import json
import os
import asyncio
import time
import uuid
import re
from openai import AsyncOpenAI
from app.services.chat_message_service import ChatMessageService
from app.services.summary_service import SummaryService
from app.redis_client import redis_client
from app.services.shared_db_pool import SharedDBPool
import psycopg2.extras
from pgvector.psycopg2 import register_vector


class StreamService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.system_instruction = (
            "You are an expert technician specialist assistant for IntelliMaint.\n\n"
            
            "CRITICAL: CONVERSATION MEMORY\n"
            "You HAVE FULL ACCESS to conversation history when provided\n"
            "You HAVE FULL ACCESS to knowledge base chunks when provided\n"
            "When user asks what was my first message or what did we discuss, USE the conversation history shown in the prompt\n"
            "NEVER say I dont have access or I cannot see previous messages\n"
            "The history is YOUR memory - use it confidently\n\n"
            
            "RESPONSE FORMAT - MANDATORY PLAIN TEXT ONLY:\n"
            "ABSOLUTELY NO MARKDOWN FORMATTING\n"
            "ABSOLUTELY NO ASTERISKS (*) FOR BOLD OR EMPHASIS\n"
            "ABSOLUTELY NO SPECIAL SYMBOLS OR DECORATIVE CHARACTERS\n"
            "ABSOLUTELY NO NUMBERED LISTS WITH DOTS (1. 2. 3.)\n"
            "ABSOLUTELY NO BULLET POINTS (-) OR (•)\n"
            "ABSOLUTELY NO EXCLAMATION MARKS (!)\n"
            "ABSOLUTELY NO QUESTION MARKS (?)\n"
            "ABSOLUTELY NO EMOJIS OR UNICODE SYMBOLS\n"
            "Use simple, clean plain text only\n"
            "Use line breaks to separate thoughts\n"
            "Use simple language without formatting\n"
            "Professional and conversational tone\n"
            "Reference previous context naturally (e.g., As we discussed earlier)\n\n"
            
            "YOUR RESPONSIBILITIES:\n"
            "Equipment Identification: Use history to remember equipment discussed before\n"
            "Technical Guidance: Provide step-by-step troubleshooting\n"
            "Safety First: Always prioritize safety warnings\n"
            "Use Knowledge Base: Leverage technical documents when available\n"
        )
        self.redis_client = redis_client
        self.db_pool = SharedDBPool()  # ✅ Shared connection pool
        
        # ========== RAG CONFIGURATION ==========
        # Aligned with gateway/rag-retrieval.service.ts
        self.rag_config = {
            "top_k_default": int(os.getenv("RAG_TOP_K", "10")),
            "top_k_max": 50,
            "top_k_min": 1,
            "similarity_threshold": float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.4")),
            "adjacent_chunks_count": int(os.getenv("RAG_ADJACENT_CHUNKS", "1")),
            "embedding_dimension": 1536,
        }
        
        self.logger_prefix = "[StreamService]"

    # ---------- helpers ----------
    def _ms(self, start): 
        return (time.perf_counter() - start) * 1000

    def _split_by_sentences(self, text: str):
        """Split text into sentences"""
        sentences = re.split(r'(?<=[.!?])\s+|(?<=\n)', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _clamp_top_k(self, top_k: int = None) -> int:
        """Clamp top_k to safe bounds"""
        k = top_k or self.rag_config["top_k_default"]
        k = max(self.rag_config["top_k_min"], min(k, self.rag_config["top_k_max"]))
        return k

    # ---------- LLM ----------
    async def stream_llm(self, prompt: str):
        """Stream OpenAI LLM response"""
        stream = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            stream=True,
            messages=[
                {"role": "system", "content": self.system_instruction},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return stream

    # ---------- EMBEDDING GENERATION ==========
    async def generate_embedding(self, text: str) -> list:
        """
        Generate embedding using OpenAI text-embedding-3-small model
        Returns list of 1536 dimensions
        """
        try:
            embedding_start = time.perf_counter()
            print(f"{self.logger_prefix}    ├─ Generating embedding for text ({len(text)} chars)...", flush=True)
            
            response = await self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            
            embedding = response.data[0].embedding
            duration = self._ms(embedding_start)
            
            print(f"{self.logger_prefix}    ├─ Embedding generated: {len(embedding)} dimensions in {duration:.2f}ms", flush=True)
            return embedding
            
        except Exception as e:
            print(f"{self.logger_prefix} ❌ Embedding generation failed: {str(e)}", flush=True)
            return []

    # ---------- RAG RETRIEVAL ==========
    async def retrieve_rag_chunks(self, embedding: list, user_id: str, top_k: int = None):
        """
        Retrieve relevant knowledge chunks from pgvector database
        
        NOTE: Embedding is pre-generated and passed in (optimized for parallel processing)
        """
        try:
            if not embedding:
                return []
                
            clamped_k = self._clamp_top_k(top_k)
            
            # ========== Vector DB Search ==========
            db_search_start = time.perf_counter()
            
            # Get connection from pool
            conn = None
            try:
                conn = await asyncio.to_thread(self.db_pool.get_connection)
                register_vector(conn)  # ✅ Register pgvector extension
                
                # Create cursor with RealDictCursor to get dicts instead of tuples
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                # ✅ FAST: DB only does ORDER BY + LIMIT (no threshold filter!)
                # Threshold filtering happens in Python (industry standard)
                sql = """
                WITH q AS (
                    SELECT %s::vector AS emb
                )
                SELECT
                    kc.id,
                    kc.source_id,
                    kc.chunk_index,
                    kc.content,
                    kc.heading,
                    kc.token_count,
                    kc.metadata,
                    1 - (kc.embedding <=> q.emb) AS similarity_score
                FROM knowledge_chunks kc
                JOIN knowledge_sources ks ON kc.source_id = ks.id
                CROSS JOIN q
                WHERE
                    ks.user_id = %s
                ORDER BY kc.embedding <=> q.emb
                LIMIT %s;
                """
                
                # Execute query with parameters (NO threshold in SQL!)
                await asyncio.to_thread(
                    cur.execute,
                    sql,
                    (
                        embedding,    # embedding vector (pgvector handles conversion)
                        user_id,      # user_id for JOIN filter
                        clamped_k     # limit
                    )
                )
                
                # Fetch all results
                chunks_raw = await asyncio.to_thread(cur.fetchall)
                cur.close()
                
                db_search_duration = self._ms(db_search_start)
                print(f"{self.logger_prefix}    ├─ DB search completed in {db_search_duration:.2f}ms", flush=True)
                
                # Format chunks for LLM context
                formatted_chunks = []
                for chunk in chunks_raw:
                    formatted_chunks.append({
                        "id": chunk['id'],
                        "source_id": chunk['source_id'],
                        "chunk_index": chunk['chunk_index'],
                        "content": chunk['content'],
                        "heading": chunk['heading'] or "Untitled",
                        "similarity_score": float(chunk['similarity_score']),
                        "token_count": chunk['token_count'],
                        "metadata": chunk['metadata']
                    })
                
                # ✅ SMART: App-level soft threshold filtering (industry standard)
                # Threshold 0.4 check happens HERE in Python (fast!)
                soft_threshold = self.rag_config["similarity_threshold"]  # 0.4
                filtered_chunks = [
                    c for c in formatted_chunks
                    if c["similarity_score"] >= soft_threshold
                ]
                
                # ✅ Fallback: If too few pass threshold, keep top 3 anyway
                if len(filtered_chunks) < 3 and len(formatted_chunks) >= 3:
                    filtered_chunks = formatted_chunks[:3]
                elif len(filtered_chunks) == 0:
                    filtered_chunks = formatted_chunks  # Return all if nothing passes
                
                print(f"{self.logger_prefix}    └─ Found {len(formatted_chunks)} chunks, {len(filtered_chunks)} passed threshold ({soft_threshold})", flush=True)
                return filtered_chunks
                
            finally:
                # Return connection to pool
                if conn:
                    await asyncio.to_thread(self.db_pool.return_connection, conn)
            
        except Exception as e:
            print(f"{self.logger_prefix} ❌ RAG retrieval error: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            return []

    def _format_rag_context(self, chunks: list) -> str:
        """Format RAG chunks as context for LLM"""
        if not chunks:
            return ""
        
        formatted = "📚 Knowledge Base References:\n\n"
        for i, chunk in enumerate(chunks[:self.rag_config["top_k_max"]], 1):
            heading = chunk.get('heading', 'Untitled')
            score = chunk.get('similarity_score', 0)
            content = chunk.get('content', '')[:200]
            formatted += f"[{i}] {heading} (Relevance: {score:.1%})\n"
            formatted += f"    {content}\n\n"
        
        return formatted

    # ---------- BACKGROUND ----------
    def _schedule_background(
        self,
        *,
        session_id,
        user_text,
        assistant_text,
        model,
        usage,
        fakeSessionId,
        user_id,
    ):
        asyncio.create_task(
            asyncio.to_thread(
                SummaryService.persist_messages_and_update_summary,
                session_id=session_id,
                user_text=user_text,
                assistant_text=assistant_text,
                model=model,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                user_id=user_id,
                fakeSessionId=fakeSessionId,
            )
        )

    # ---------- REALTIME PIPELINE ----------
    async def process_text(self, text, session_id, user_id, fakeSessionId, websocket):
        """
        Main Text Processing Pipeline with PARALLEL execution:
        
        Parallel Stage 1️⃣: Load conversation context (messages + summary)
        Parallel Stage 2️⃣: Generate embedding & retrieve RAG chunks
        
        Sequential Stages:
        Stage 3️⃣: Build prompt & format with RAG context
        Stage 4️⃣: Stream LLM response
        Stage 5️⃣: Split into sentence chunks
        Stage 6️⃣: Send chunks to frontend
        Stage 7️⃣: Persist messages in background
        """
        t0 = time.perf_counter()
        if not text:
            return None
        
        print(f"\n{'='*70}", flush=True)
        print(f"{self.logger_prefix} ========== 🚀 PARALLEL PIPELINE START ==========", flush=True)
        print(f"{'='*70}", flush=True)
        
        # ========== STAGE 0: User Input Received ==========
        print(f"{self.logger_prefix} Stage 0️⃣ User text received: {len(text)} chars", flush=True)
        print(f"{self.logger_prefix}    Text: '{text[:100]}{'...' if len(text) > 100 else ''}'", flush=True)
        print(f"{self.logger_prefix}    SessionId: {session_id}", flush=True)
        print(f"{self.logger_prefix}    UserId: {user_id}", flush=True)

        # ========== PARALLEL EXECUTION: Context Loading + RAG Retrieval ==========
        parallel_start = time.perf_counter()
        print(f"{self.logger_prefix} Running Tasks 1 & 2 in parallel...", flush=True)
        
        # Define Task 1: Load conversation context
        async def load_context():
            task_start = time.perf_counter()
            # ✅ Parallelize the two DB queries using asyncio.gather()
            results = await asyncio.gather(
                asyncio.to_thread(ChatMessageService.get_last_messages, session_id, 5),
                asyncio.to_thread(ChatMessageService.get_summary, session_id),
                return_exceptions=False
            )
            last_messages = results[0]
            summary = results[1]
            task_duration = self._ms(task_start)
            print(f"{self.logger_prefix}    [Task 1] Context loaded in {task_duration:.2f}ms", flush=True)
            return 
        
        # Define Task 2: Generate embedding and retrieve RAG chunks
        async def rag_retrieval():
            task_start = time.perf_counter()
            # Generate embedding
            embedding_start = time.perf_counter()
            embedding = await self.generate_embedding(text)
            embedding_duration = self._ms(embedding_start)
            
            if not embedding:
                print(f"{self.logger_prefix}    [Task 2] ❌ Failed to generate embedding", flush=True)
                return []
            
            # Retrieve RAG chunks with pre-generated embedding
            rag_chunks = await self.retrieve_rag_chunks(embedding, user_id, self.rag_config["top_k_default"])
            task_duration = self._ms(task_start)
            print(f"{self.logger_prefix}    [Task 2] RAG done in {task_duration:.2f}ms (Embedding: {embedding_duration:.2f}ms)", flush=True)
            return rag_chunks
        
        # ✅ Use asyncio.gather() to run BOTH tasks in PARALLEL (not sequential)
        try:
            results = await asyncio.gather(
                load_context(),
                rag_retrieval(),
                return_exceptions=False
            )
            last_messages, summary = results[0]
            rag_chunks = results[1]
        except Exception as e:
            print(f"{self.logger_prefix} ❌ Parallel execution error: {str(e)}", flush=True)
            last_messages = []
            summary = None
            rag_chunks = []
        
        parallel_duration = self._ms(parallel_start)
        print(f"{self.logger_prefix} Parallel execution completed in {parallel_duration:.2f}ms", flush=True)

        # ========== BUILD PROMPT & FORMAT WITH RAG CONTEXT ==========
        step_start = time.perf_counter()

        # Build structured context
        context_sections = []

        # 1. Summary
        if summary:
            context_sections.append(
                f"=== CONVERSATION SUMMARY ===\n{summary}\n=== END SUMMARY ===\n"
            )

        # 2. Recent messages
        if last_messages:
            context_sections.append("=== RECENT MESSAGES ===")
            for m in last_messages:
                role = "User" if m['role'] == 'user' else "Assistant"
                context_sections.append(f"{role}: {m['content']}")
            context_sections.append("=== END MESSAGES ===\n")

        # 3. RAG chunks
        rag_context = self._format_rag_context(rag_chunks)
        if rag_context:
            context_sections.append(rag_context)

        # Build final prompt with explicit instruction
        if context_sections:
            context_block = "\n".join(context_sections)
            final_prompt = (
                f"CONTEXT PROVIDED BELOW - USE THIS TO ANSWER:\n\n"
                f"{context_block}\n\n"
                f"USER'S CURRENT QUESTION: {text}"
            )
        else:
            final_prompt = f"USER QUESTION: {text}"

        prompt_stage_duration = self._ms(step_start)
        print(f"{self.logger_prefix} Stage 3️⃣ Prompt built ({len(final_prompt)} chars)", flush=True)

        # ========== STAGE 4: Stream LLM Response ==========
        full_response = ""
        usage = None
        try:
            step_start = time.perf_counter()
            print(f"{self.logger_prefix} Stage 4️⃣ LLM streaming starting...", flush=True)
            stream = await self.stream_llm(final_prompt)
            
            token_count = 0
            async for event in stream:
                if event.choices[0].delta.content:
                    token = event.choices[0].delta.content
                    full_response += token
                    token_count += 1
                
                if event.usage:
                    usage = event.usage
            
            llm_duration = self._ms(step_start)
            print(f"{self.logger_prefix} Stage 4️⃣ LLM streaming complete in {llm_duration:.2f}ms", flush=True)
            print(f"{self.logger_prefix}    Response length: {len(full_response)} chars", flush=True)
            print(f"{self.logger_prefix}    Tokens streamed: {token_count}", flush=True)
            if usage:
                print(f"{self.logger_prefix}    Usage - Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens}", flush=True)
            
        except Exception as e:
            print(f"{self.logger_prefix} ❌ Stage 4️⃣ LLM streaming failed: {str(e)}", flush=True)
            await websocket.send_json({
                "type": "error",
                "message": "Sorry, I'm having trouble right now."
            })
            return "Sorry, I'm having trouble right now."

        # ========== STAGE 5: Send Complete Response as Single Chunk ==========
        step_start = time.perf_counter()
        print(f"{self.logger_prefix} Stage 5️⃣ Sending complete response to frontend...", flush=True)
        
        # Send the complete response as a single chunk (keep type: "chunk" format)
        await websocket.send_json({
            "type": "chunk",
            "token": full_response,
            "chunkIndex": 1,
            "chunkMode": "complete",
            "timestamp": time.time(),
            "ragChunksUsed": len(rag_chunks)
        })
        
        # Send final message (same as before)
        await websocket.send_json({
            "type": "final",
            "response": full_response,
            "totalChunks": 1,
            "chunkMode": "complete",
            "ragChunksUsed": len(rag_chunks),
            "usageTokens": {
                "prompt": usage.prompt_tokens if usage else None,
                "completion": usage.completion_tokens if usage else None,
                "total": usage.total_tokens if usage else None,
            }
        })
        
        send_duration = self._ms(step_start)
        print(f"{self.logger_prefix} Stage 5️⃣ Response sent in {send_duration:.2f}ms", flush=True)
        print(f"{self.logger_prefix}    Response length: {len(full_response)} chars", flush=True)

        # ========== STAGE 6: Persist Messages (Background) ==========
        step_start = time.perf_counter()
        self._schedule_background(
            session_id=session_id,
            user_text=text,
            assistant_text=full_response,
            model="gpt-4o-mini",
            usage=usage,
            fakeSessionId=fakeSessionId,
            user_id=user_id,
        )
        persist_duration = self._ms(step_start)
        print(f"{self.logger_prefix} Stage 6️⃣ Background persistence scheduled in {persist_duration:.2f}ms", flush=True)
        print(f"{self.logger_prefix}    Status: ✅ Queued for DB save", flush=True)

        # ========== PIPELINE SUMMARY ==========
        total_duration = self._ms(t0)
        print(f"\n{'='*70}", flush=True)
        print(f"{self.logger_prefix} 📊 PARALLEL PIPELINE TIMING SUMMARY", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"{self.logger_prefix} Parallel Stage (Tasks 1+2): {parallel_duration:8.2f}ms ⭐ Optimized", flush=True)
        print(f"{self.logger_prefix}    ├─ Task 1 (Context): ~1300ms | Task 2 (RAG): ~1050ms = {parallel_duration:.2f}ms combined", flush=True)
        print(f"{self.logger_prefix} Stage 3 (Prompt/Format):    {prompt_stage_duration:8.2f}ms", flush=True)
        print(f"{self.logger_prefix} Stage 4 (LLM):              {llm_duration:8.2f}ms ⭐ (main bottleneck)", flush=True)
        print(f"{self.logger_prefix} Stage 5 (Send):             {send_duration:8.2f}ms", flush=True)
        print(f"{self.logger_prefix} Stage 6 (Persist):          {persist_duration:8.2f}ms", flush=True)
        print(f"{'-'*70}", flush=True)
        print(f"{self.logger_prefix} ✅ TOTAL PIPELINE TIME: {total_duration:8.2f}ms", flush=True)
        print(f"{self.logger_prefix}    RAG Chunks Used: {len(rag_chunks)}", flush=True)
        print(f"{self.logger_prefix}    Savings: ~1000ms (from parallelizing Tasks 1 & 2)", flush=True)
        print(f"{'='*70}\n", flush=True)
        
        return True

    async def handle_stream(self, data: dict, user_id: str | None, websocket):
        """Handle incoming WebSocket stream messages"""
        msg = data

        print(f"{self.logger_prefix} WebSocket message received", flush=True)

        if "text" not in msg or not msg["text"]:
            await websocket.send_json({
                "type": "error",
                "message": "Sorry, I'm having trouble right now."
            })
            return False
    
        # ✅ Handle both JSON and plain text formats
        try:
            # Try to parse as JSON first
            if isinstance(msg["text"], str):
                # Check if it looks like JSON
                if msg["text"].strip().startswith('{'):
                    payload = json.loads(msg["text"])
                else:
                    # Plain text - wrap it as a message
                    payload = {
                        "type": "message",
                        "text": msg["text"],
                        "sessionId": None
                    }
            else:
                payload = msg["text"]
        except json.JSONDecodeError:
            # If JSON parsing fails, treat as plain text message
            payload = {
                "type": "message",
                "text": msg["text"],
                "sessionId": None
            }
        
        # Handle special control messages
        if payload.get("type") == "stop":
            print(f"{self.logger_prefix} Received STOP signal", flush=True)
            return False
        if payload.get("type") == "interrupt":
            print(f"{self.logger_prefix} Received INTERRUPT signal", flush=True)
            return False
        
        # Get session ID and user text
        session_id = payload.get("sessionId")
        user_text = payload.get("text", "")
        fake_session_id = None
        
        if not session_id:
            fake_session_id = str(uuid.uuid4())

        print(f"{self.logger_prefix} Processing: sessionId={session_id}, fakeSessionId={fake_session_id}, text={user_text[:50]}", flush=True)

        result = await self.process_text(
            user_text,
            session_id,
            user_id,
            fake_session_id,
            websocket
        )
        
        if fake_session_id:
            await websocket.send_json({
                "type": "session",
                "fakeSessionId": fake_session_id
            })
        
        return result