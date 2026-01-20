# import json
# import os
# import asyncio
# import time
# import uuid
# from openai import AsyncOpenAI
# from app.services.asr_tts_service import synthesize_speech
# from app.services.chat_message_service import ChatMessageService
# from app.services.summary_service import SummaryService
# from app.redis_client import redis_client
# import uuid


# class StreamService:
#     def __init__(self):
#         self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#         self.system_instruction = (
#             "You are an expert technician specialist assistant for IntelliMaint, providing professional guidance for equipment maintenance, troubleshooting, and repair via voice interaction.\n\n"
#             "🔐 CRITICAL - YOU HAVE FULL ACCESS TO CONVERSATION HISTORY:\n"
#             "The user's previous messages and conversation summary are provided to you in this very prompt.\n"
#             "You DO have complete access to all previous context. NEVER say you don't have access.\n"
#             "If the summary or messages are included, assume they are accurate and use them AS THE SOURCE OF TRUTH.\n"
#             "The user is recalling their previous conversation with you - reference it naturally and directly.\n\n"
#             "YOUR RESPONSIBILITIES:\n"
#             "1. **Equipment Identification & Analysis**:\n"
#             "   - If users describe equipment, identify make/model/type from description\n"
#             "   - Reference PREVIOUS CONVERSATIONS - remember equipment they've discussed before\n"
#             "   - Ask for specific details only if NOT already provided in history\n"
#             "   - Build expertise on their specific equipment as conversation progresses\n\n"
#             "2. **Professional Technical Guidance**:\n"
#             "   - Provide step-by-step troubleshooting procedures\n"
#             "   - Explain technical concepts clearly for both novice and experienced technicians\n"
#             "   - Include safety warnings for electrical, mechanical, or hazardous systems\n"
#             "   - Reference industry standards and best practices\n"
#             "   - Suggest specific tools, parts, or materials needed\n\n"
#             "3. **USING CONVERSATION HISTORY - MANDATORY**:\n"
#             "   - If a summary is provided: Use it to recall what was discussed in PREVIOUS SESSIONS\n"
#             "   - If recent messages are provided: Reference them directly in your response\n"
#             "   - CONNECT current problem to past issues/solutions discussed\n"
#             "   - Build continuity: \"As we discussed earlier...\", \"Remember when you asked about...\", etc.\n"
#             "   - If user asks about something from previous chat - YOU HAVE THAT INFO - use it!\n\n"
#             "4. **Voice Interaction Style**:\n"
#             "   - Keep responses concise but complete (30-60 seconds average)\n"
#             "   - Use natural spoken language, avoid long lists\n"
#             "   - Break complex procedures into short spoken steps\n"
#             "   - Be conversational yet professional\n"
#             "   - When referencing previous context, say it naturally (\"Earlier you mentioned...\")\n\n"
#             "5. **Safety & Quality**:\n"
#             "   - ALWAYS prioritize safety first\n"
#             "   - Recommend proper lockout/tagout procedures\n"
#             "   - Emphasize PPE (Personal Protective Equipment)\n"
#             "   - Follow manufacturer guidelines\n"
#             "   - Warn about risks before suggesting procedures\n\n"
#             "⭐ KEY RULES:\n"
#             "- You have context provided in this prompt. Use it.\n"
#             "- NEVER say \"I don't have access\" or \"I can't see previous messages\"\n"
#             "- If history is provided, it means the user expects you to remember it\n"
#             "- Speak as if you ARE recalling the previous conversation\n"
#             "- Connect the current question to previous context naturally\n\n"
#             "TONE: Professional, helpful, authoritative, safety-conscious, with continuity from previous interactions."
#         )

#         self.redis_client = redis_client

#     # ---------- helpers ----------
#     def _ms(self, start): 
#         return (time.perf_counter() - start) * 1000

#     # ---------- LLM ----------
#     async def call_llm(self, prompt: str):
#         # 🔴 DEBUG: Log what we're sending to LLM
#         print('\n' + '='*80, flush=True)
#         print('🚀 [LLM CALL] Sending to OpenAI API', flush=True)
#         print('='*80, flush=True)
#         print(f'📊 Prompt Length: {len(prompt)} characters', flush=True)
        
#         # Check if summary exists in prompt
#         if 'SYSTEM CONTEXT:' in prompt:
#             context_start = prompt.find('SYSTEM CONTEXT:')
#             context_end = prompt.find('\nThe messages below')
#             summary_section = prompt[context_start:context_end]
#             print(f'✅ SUMMARY INCLUDED: YES', flush=True)
#             print(f'   Summary Section Length: {len(summary_section)} chars', flush=True)
#             print(f'   Summary Preview: {summary_section[:200]}...', flush=True)
#         else:
#             print(f'❌ SUMMARY INCLUDED: NO - This is why LLM says it has no access!', flush=True)
        
#         print(f'\n📝 Full Prompt:\n{prompt}\n', flush=True)
#         print('='*80 + '\n', flush=True)
        
#         resp = await self.client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": self.system_instruction},
#                 {"role": "user", "content": prompt},
#             ],
#             temperature=0.3,
#         )
#         return resp.choices[0].message.content, resp.usage

#     async def text_to_audio(self, text: str) -> bytes:
#         return await synthesize_speech(text)

#     async def _safe_error_reply(self):
#         try:
#             return await self.text_to_audio("Sorry, I'm having trouble right now.")
#         except Exception:
#             return "Sorry, I'm having trouble right now."

#     # ---------- BACKGROUND ----------
#     def _schedule_background(
#         self,
#         *,
#         session_id,
#         user_text,
#         assistant_text,
#         model,
#         usage,
#         fakeSessionId,
#         user_id,
#     ):
#         asyncio.create_task(
#             asyncio.to_thread(
#                 SummaryService.persist_messages_and_update_summary,
#                 session_id=session_id,
#                 user_text=user_text,
#                 assistant_text=assistant_text,
#                 model=model,
#                 prompt_tokens=usage.prompt_tokens if usage else None,
#                 completion_tokens=usage.completion_tokens if usage else None,
#                 total_tokens=usage.total_tokens if usage else None,
#                 user_id=user_id,
#                 fakeSessionId=fakeSessionId,
#             )
#         )

#     # For Create new Session + new ChatMessage records

    

#     # ---------- REALTIME ----------
#     async def process_text(self, text, session_id, user_id, fakeSessionId):
#         t0 = time.perf_counter()
#         if not text:
#             return None
        

#         # 1️⃣ Context read (fast)
#         step_start = time.perf_counter()
#         last_messages = ChatMessageService.get_last_messages(session_id, 5)
#         summary = ChatMessageService.get_summary(session_id)
#         print(f"[TIMING] db_context_read: {self._ms(step_start):.2f} ms", flush=True)
        
#         # 🔴 DEBUG: Log what we retrieved from database
#         print('\n' + '='*80, flush=True)
#         print(f'📚 [DEBUG] Context Retrieved from Database', flush=True)
#         print('='*80, flush=True)
#         print(f'📌 Session ID: {session_id}', flush=True)
#         print(f'📊 Last Messages Count: {len(last_messages) if last_messages else 0}', flush=True)
#         print(f'📋 Summary Available: {bool(summary)}', flush=True)
#         if summary:
#             print(f'   Summary Length: {len(summary)} chars', flush=True)
#             print(f'   Summary Preview: {summary[:150]}...', flush=True)
#         else:
#             print(f'   ⚠️ Summary is EMPTY/NULL - This is the problem!', flush=True)
#         print('='*80 + '\n', flush=True)

#         # 2️⃣ Prompt build
#         step_start = time.perf_counter()
#         parts = []
#         if summary:
#             print(f'✅ Adding SYSTEM CONTEXT to prompt', flush=True)
#             parts.append(
#             "SYSTEM CONTEXT:\n"
#             "The following is an accurate summary of the user's past conversation.\n"
#             "You DO have access to this information and should use it as the source of truth.\n\n"
#             f"{summary}"
#                 )
#         else:
#             print(f'❌ NO SYSTEM CONTEXT - Summary is None/empty', flush=True)
#         parts.append(
#             "\nThe messages below are the most recent exchanges in THIS session:\n"
#         )
#         for m in last_messages:
#             parts.append(f"{m['role']}: {m['content']}")
#         parts.append(f"user: {text}")
#         prompt = "\n".join(parts)
#         print(f"[TIMING] prompt_build: {self._ms(step_start):.2f} ms", flush=True)
#         print(f'[PROMPT SIZE] Total prompt: {len(prompt)} chars', flush=True)

#         # 3️⃣ LLM
#         try:
#             step_start = time.perf_counter()
#             reply, usage = await self.call_llm(prompt)
#             print(f"[TIMING] llm_call: {self._ms(step_start):.2f} ms", flush=True)
#             print(f"[LLM Reply]: {reply}", flush=True)
#         except Exception:
#             return await self._safe_error_reply()

#         # 4️⃣ TTS
#         try:
#             step_start = time.perf_counter()
#             audio = await self.text_to_audio(reply)
#             print(f"[TIMING] tts_call: {self._ms(step_start):.2f} ms", flush=True)
#         except Exception:
#             return await self._safe_error_reply()

#         # 5️⃣ BACKGROUND DB + SUMMARY (NON-BLOCKING)
#         step_start = time.perf_counter()
#         self._schedule_background(
#             session_id=session_id,
#             user_text=text,
#             assistant_text=reply,
#             model="gpt-4o-mini",
#             usage=usage,
#             fakeSessionId=fakeSessionId,
#             user_id=user_id,
#         )
#         print(
#             f"[TIMING] background_task_scheduling: {self._ms(step_start):.2f} ms",
#             flush=True,
#         )

#         print(f"[TIMING] process_text_total: {self._ms(t0):.2f} ms", flush=True)
#         return audio

#     async def handle_stream(self, data: dict, user_id: str | None):
#         msg = data

#         print(f"[stream_service] handle_stream: received message: {msg}", flush=True)

#         if "text" not in msg or not msg["text"]:
#             return await self._safe_error_reply() 
    
#         if "text" in msg and msg["text"]:
#             payload = json.loads(msg["text"])   # 👈 important
#             if payload.get("type") == "stop":
#                 print("[stream_service] handle_stream: received 'stop' message, returning.", flush=True)
#                 return False
#                         # ✅ Handle interrupt message - just return False, no fake_session_id needed
#             if payload.get("type") == "interrupt":
#                 print("[stream_service] handle_stream: received 'interrupt' message, returning.", flush=True)
#                 return False
#         session_id = payload.get("sessionId")
#         fake_session_id = None
#         if not session_id:
#             fake_session_id = str(uuid.uuid4())

#         print(f"[stream_service] handle_stream: session_id={session_id}", flush=True)
#         print(f"fake_session_id={fake_session_id}", flush=True)

#         # return False

#         result = await self.process_text(
#             payload.get("text", ""),
#             session_id,
#             user_id,
#             fake_session_id
#         )
#         # If a fake session was generated, return it separately
#         if fake_session_id:
#             # Return both the result and fake_session_id as a tuple
#             return (result, fake_session_id)
        
#         return result
       
from email.mime import text
from email.mime import text
import json
import os
import asyncio
import time
import uuid
from openai import AsyncOpenAI
from app.services.asr_tts_service import synthesize_speech
from app.services.chat_message_service import ChatMessageService
from app.services.summary_service import SummaryService
from app.services.shared_db_pool import SharedDBPool
from app.redis_client import redis_client
from psycopg2.extras import RealDictCursor


class StreamService:
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.system_instruction = (
            "You are an expert technician specialist assistant for IntelliMaint, providing professional guidance for equipment maintenance, troubleshooting, and repair via voice interaction.\n\n"
            "🔍 CRITICAL - YOU HAVE FULL ACCESS TO CONVERSATION HISTORY AND KNOWLEDGE BASE:\n"
            "The user's previous messages, conversation summary, and RELEVANT KNOWLEDGE BASE chunks are provided to you in this very prompt.\n"
            "You DO have complete access to all previous context AND technical knowledge. NEVER say you don't have access.\n"
            "If the summary, messages, or knowledge chunks are included, assume they are accurate and use them AS THE SOURCE OF TRUTH.\n"
            "The user is recalling their previous conversation with you - reference it naturally and directly.\n\n"
            "YOUR RESPONSIBILITIES:\n"
            "1. **Equipment Identification & Analysis**:\n"
            "   - If users describe equipment, identify make/model/type from description\n"
            "   - Reference PREVIOUS CONVERSATIONS - remember equipment they've discussed before\n"
            "   - Use KNOWLEDGE BASE chunks when available for technical specifications\n"
            "   - Ask for specific details only if NOT already provided in history or knowledge base\n"
            "   - Build expertise on their specific equipment as conversation progresses\n\n"
            "2. **Professional Technical Guidance**:\n"
            "   - Provide step-by-step troubleshooting procedures\n"
            "   - Explain technical concepts clearly for both novice and experienced technicians\n"
            "   - Include safety warnings for electrical, mechanical, or hazardous systems\n"
            "   - Reference industry standards and best practices from knowledge base\n"
            "   - Suggest specific tools, parts, or materials needed\n\n"
            "3. **USING CONVERSATION HISTORY & KNOWLEDGE BASE - MANDATORY**:\n"
            "   - If a summary is provided: Use it to recall what was discussed in PREVIOUS SESSIONS\n"
            "   - If recent messages are provided: Reference them directly in your response\n"
            "   - If KNOWLEDGE BASE chunks are provided: Prioritize them for technical accuracy\n"
            "   - CONNECT current problem to past issues/solutions discussed\n"
            "   - Build continuity: \"As we discussed earlier...\", \"According to the manual...\", etc.\n"
            "   - If user asks about something from previous chat - YOU HAVE THAT INFO - use it!\n\n"
            "4. **Voice Interaction Style**:\n"
            "   - Keep responses concise but complete (30-60 seconds average)\n"
            "   - Use natural spoken language, avoid long lists\n"
            "   - Break complex procedures into short spoken steps\n"
            "   - Be conversational yet professional\n"
            "   - When referencing previous context or knowledge base, say it naturally\n\n"
            "5. **Safety & Quality**:\n"
            "   - ALWAYS prioritize safety first\n"
            "   - Recommend proper lockout/tagout procedures\n"
            "   - Emphasize PPE (Personal Protective Equipment)\n"
            "   - Follow manufacturer guidelines from knowledge base\n"
            "   - Warn about risks before suggesting procedures\n\n"
            "⭐ KEY RULES:\n"
            "- You have context AND knowledge base provided in this prompt. Use them.\n"
            "- NEVER say \"I don't have access\" or \"I can't see previous messages\"\n"
            "- If history/knowledge is provided, the user expects you to remember/use it\n"
            "- Speak as if you ARE recalling previous conversation and technical docs\n"
            "- Connect current question to previous context and knowledge naturally\n\n"
            "TONE: Professional, helpful, authoritative, safety-conscious, with continuity from previous interactions and technical accuracy from knowledge base."
        )
        self.redis_client = redis_client
        self.db_url = os.getenv("DATABASE_URL")

    # ---------- helpers ----------
    def _ms(self, start): 
        return (time.perf_counter() - start) * 1000

    # # ---------- RAG METHODS ----------
    # async def generate_embedding(self, text: str):
    #     """Generate 1536-dim embedding for user text using OpenAI API"""
    #     step_start = time.perf_counter()
    #     try:
    #         response = await self.client.embeddings.create(
    #             model="text-embedding-3-small",
    #             input=text,
    #             encoding_format="float"
    #         )
    #         embedding = response.data[0].embedding
    #         print(f"[TIMING] ✅ generate_embedding: {self._ms(step_start):.2f} ms", flush=True)
    #         return embedding
    #     except Exception as e:
    #         print(f"[RAG] ❌ Embedding generation failed: {e}", flush=True)
    #         print(f"[TIMING] ❌ generate_embedding (failed): {self._ms(step_start):.2f} ms", flush=True)
    #         return None

    # def retrieve_knowledge_chunks(self, embedding, user_id: str, top_k: int = 10):
    #     """Retrieve top-K chunks using pgvector cosine similarity"""
    #     step_start = time.perf_counter()
        
    #     if not embedding:
    #         print(f"[RAG] ⚠️ No embedding provided, skipping retrieval", flush=True)
    #         return []
        
    #     conn = None
    #     try:
    #         # Get connection from shared pool
    #         conn = SharedDBPool.get_connection()
    #         cur = conn.cursor(cursor_factory=RealDictCursor)
            
    #         # pgvector cosine similarity query
    #         # <=> operator calculates cosine distance (lower = more similar)
    #         query = """
    #             SELECT 
    #                 kc.id,
    #                 kc.content,
    #                 kc.chunk_index,
    #                 ks.title as source_title,
    #                 (kc.embedding <=> %s::vector) as distance
    #             FROM knowledge_chunks kc
    #             JOIN knowledge_sources ks ON kc.source_id = ks.id
    #             WHERE ks.user_id = %s 
    #               AND kc.embedding IS NOT NULL
    #             ORDER BY kc.embedding <=> %s::vector
    #             LIMIT %s;
    #         """
            
    #         # Convert embedding list to pgvector format string
    #         embedding_str = str(embedding)
            
    #         cur.execute(query, (embedding_str, user_id, embedding_str, top_k))
    #         chunks = cur.fetchall()
            
    #         cur.close()
    #         SharedDBPool.return_connection(conn)  # Return connection to shared pool
            
    #         print(f"[TIMING] ✅ retrieve_knowledge_chunks: {self._ms(step_start):.2f} ms", flush=True)
    #         print(f"[RAG] 📦 Retrieved {len(chunks)} chunks from knowledge base", flush=True)
            
    #         return chunks
            
    #     except Exception as e:
    #         print(f"[RAG] ❌ Vector search failed: {e}", flush=True)
    #         print(f"[TIMING] ❌ retrieve_knowledge_chunks (failed): {self._ms(step_start):.2f} ms", flush=True)
    #         if conn:
    #             try:
    #                 SharedDBPool.return_connection(conn)
    #             except:
    #                 pass
    #         return []

    # def format_chunks_for_llm(self, chunks):
    #     """Format retrieved chunks for LLM context (600 char limit per chunk)"""
    #     step_start = time.perf_counter()
        
    #     if not chunks:
    #         return ""
        
    #     formatted_parts = ["RELEVANT KNOWLEDGE BASE:\n"]
        
    #     for idx, chunk in enumerate(chunks, 1):
    #         content = chunk.get('content', '')
    #         source_title = chunk.get('source_title', 'Unknown')
    #         distance = chunk.get('distance', 0)
            
    #         # Truncate to 600 chars (Gateway standard)
    #         if len(content) > 600:
    #             content = content[:597] + "..."
            
    #         formatted_parts.append(
    #             f"[{idx}] Source: {source_title}\n"
    #             f"    Relevance: {1 - distance:.2f}\n"
    #             f"    {content}\n"
    #         )
        
    #     result = "\n".join(formatted_parts)
    #     print(f"[TIMING] ✅ format_chunks_for_llm: {self._ms(step_start):.2f} ms", flush=True)
    #     print(f"[RAG] 📝 Formatted chunks total size: {len(result)} chars", flush=True)
        
    #     return result

    # ---------- LLM ----------
    async def call_llm(self, prompt: str):
        # 🔴 DEBUG: Log what we're sending to LLM
        print('\n' + '='*80, flush=True)
        print('🚀 [LLM CALL] Sending to OpenAI API', flush=True)
        print('='*80, flush=True)
        print(f'📊 Prompt Length: {len(prompt)} characters', flush=True)
        
        # Check if summary exists in prompt
        if 'SYSTEM CONTEXT:' in prompt:
            context_start = prompt.find('SYSTEM CONTEXT:')
            context_end = prompt.find('\nThe messages below') if '\nThe messages below' in prompt else prompt.find('\nRELEVANT KNOWLEDGE BASE:')
            summary_section = prompt[context_start:context_end] if context_end > 0 else prompt[context_start:context_start+200]
            print(f'✅ SUMMARY INCLUDED: YES', flush=True)
            print(f'   Summary Section Length: {len(summary_section)} chars', flush=True)
            print(f'   Summary Preview: {summary_section[:200]}...', flush=True)
        else:
            print(f'❌ SUMMARY INCLUDED: NO', flush=True)
        
        # Check if knowledge base exists
        if 'RELEVANT KNOWLEDGE BASE:' in prompt:
            kb_start = prompt.find('RELEVANT KNOWLEDGE BASE:')
            kb_end = prompt.find('\nThe messages below') if '\nThe messages below' in prompt else len(prompt)
            kb_section = prompt[kb_start:kb_end]
            print(f'✅ KNOWLEDGE BASE INCLUDED: YES', flush=True)
            print(f'   KB Section Length: {len(kb_section)} chars', flush=True)
        else:
            print(f'⚠️ KNOWLEDGE BASE INCLUDED: NO', flush=True)
        
        print(f'\n🔍 Full Prompt:\n{prompt}\n', flush=True)
        print('='*80 + '\n', flush=True)
        
        resp = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self.system_instruction},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content, resp.usage

    async def text_to_audio(self, text: str) -> bytes:
        return await synthesize_speech(text)

    async def _safe_error_reply(self):
        try:
            return await self.text_to_audio("Sorry, I'm having trouble right now.")
        except Exception:
            return "Sorry, I'm having trouble right now."

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
        
        
    async def process_text_streaming(
        self,
        text: str,
        session_id: str | None,
        user_id: str | None,
        websocket,
        fakeSessionId: str | None = None,
    ):
        if not text:
            return

        # 🚀 MAIN TIMER START
        pipeline_start = time.perf_counter()
        print("\n" + "="*80, flush=True)
        print("🔥 [STREAMING] Starting low-latency pipeline", flush=True)
        print("="*80, flush=True)

        # 1️⃣ Context retrieval
        context_start = time.perf_counter()
        # last_messages = ChatMessageService.get_last_messages(session_id, 5)
        # summary = ChatMessageService.get_summary(session_id)
        last_messages_task = asyncio.to_thread(
            ChatMessageService.get_last_messages,
            session_id,
            5
        )
        summary_task = asyncio.to_thread(
            ChatMessageService.get_summary,
            session_id
        )

        last_messages, summary = await asyncio.gather(
            last_messages_task,
            summary_task
        )

        context_time = self._ms(context_start)
        print(f"⏱️  [1. DATABASE CONTEXT] Fetched in: {context_time:.2f} ms", flush=True)
        print(f"   📊 Last messages: {len(last_messages) if last_messages else 0} messages", flush=True)
        print(f"   📋 Summary available: {'YES' if summary else 'NO'}", flush=True)

        # 2️⃣ Prompt building
        prompt_start = time.perf_counter()
        parts = []
        if summary:
            parts.append(
                "SYSTEM CONTEXT:\n"
                "The following is an accurate summary of the user's past conversation.\n"
                f"{summary}\n"
            )

        parts.append("\nRecent conversation:\n")
        for m in last_messages:
            parts.append(f"{m['role']}: {m['content']}")

        parts.append(f"user: {text}")
        prompt = "\n".join(parts)
        prompt_time = self._ms(prompt_start)
        print(f"⏱️  [2. PROMPT BUILD] Built in: {prompt_time:.2f} ms", flush=True)
        print(f"   📝 Prompt size: {len(prompt)} characters", flush=True)

        # 3️⃣ LLM Stream initialization
        llm_init_start = time.perf_counter()
        stream = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            stream=True,
            messages=[
                {"role": "system", "content": self.system_instruction},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        llm_init_time = self._ms(llm_init_start)
        print(f"⏱️  [3. LLM INIT] Connection ready in: {llm_init_time:.2f} ms", flush=True)

        buffer = ""
        full_response = ""
        sentence_count = 0
        total_tts_time = 0
        total_websocket_time = 0

        from app.services.asr_tts_service import get_deepgram_service
        dg = get_deepgram_service()

        # 4️⃣ Stream processing
        stream_start = time.perf_counter()
        print(f"⏱️  [4. STREAM PROCESSING] Starting...", flush=True)

        async for event in stream:
            delta = event.choices[0].delta.content
            if not delta:
                continue

            buffer += delta
            full_response += delta

            # Sentence boundary
            if any(buffer.endswith(ending) for ending in (".", "?", "!", "\n")):
                sentence = buffer.strip()
                buffer = ""

                if sentence:
                    sentence_count += 1
                    sentence_start = time.perf_counter()
                    
                    print(f"\n📨 [SENTENCE {sentence_count}] Processing: '{sentence[:50]}...'", flush=True)

                    # Send text to websocket
                    ws_send_start = time.perf_counter()
                    await websocket.send_text(json.dumps({
                        "type": "text",
                        "content": sentence
                    }))
                    ws_send_time = self._ms(ws_send_start)
                    total_websocket_time += ws_send_time
                    print(f"   ⏱️  Text sent to WebSocket: {ws_send_time:.2f} ms", flush=True)

                    # ✅ Stream audio chunks for this sentence
                    try:
                        tts_start = time.perf_counter()
                        chunk_count = 0
                        async for audio_chunk in dg.stream_tts(sentence):
                            if audio_chunk and len(audio_chunk) > 0:
                                chunk_send_start = time.perf_counter()
                                # Send raw bytes (frontend uses ArrayBuffer now)
                                await websocket.send_bytes(audio_chunk)
                                chunk_time = self._ms(chunk_send_start)
                                total_websocket_time += chunk_time
                                chunk_count += 1
                        
                        tts_time = self._ms(tts_start)
                        total_tts_time += tts_time
                        print(f"   ⏱️  TTS generated + sent: {tts_time:.2f} ms ({chunk_count} chunks)", flush=True)
                        
                        # ✅ Signal sentence complete
                        ws_complete_start = time.perf_counter()
                        await websocket.send_text(json.dumps({
                            "type": "sentence_complete"
                        }))
                        ws_complete_time = self._ms(ws_complete_start)
                        total_websocket_time += ws_complete_time
                        print(f"   ⏱️  Sentence complete signal: {ws_complete_time:.2f} ms", flush=True)
                        
                        sentence_total = self._ms(sentence_start)
                        print(f"   ✅ Sentence {sentence_count} total time: {sentence_total:.2f} ms", flush=True)
                        
                    except Exception as e:
                        print(f"   ❌ TTS streaming error: {e}", flush=True)

        stream_time = self._ms(stream_start)

        # 5️⃣ Flush remaining buffer
        flush_start = time.perf_counter()
        if buffer.strip():
            sentence_count += 1
            remaining = buffer.strip()
            print(f"\n📨 [SENTENCE {sentence_count} - FINAL] Processing: '{remaining[:50]}...'", flush=True)

            ws_send_start = time.perf_counter()
            await websocket.send_text(json.dumps({
                "type": "text",
                "content": remaining
            }))
            ws_send_time = self._ms(ws_send_start)
            total_websocket_time += ws_send_time
            print(f"   ⏱️  Text sent to WebSocket: {ws_send_time:.2f} ms", flush=True)

            try:
                tts_start = time.perf_counter()
                chunk_count = 0
                async for audio_chunk in dg.stream_tts(remaining):
                    if audio_chunk and len(audio_chunk) > 0:
                        chunk_send_start = time.perf_counter()
                        await websocket.send_bytes(audio_chunk)
                        chunk_time = self._ms(chunk_send_start)
                        total_websocket_time += chunk_time
                        chunk_count += 1
                
                tts_time = self._ms(tts_start)
                total_tts_time += tts_time
                print(f"   ⏱️  TTS generated + sent: {tts_time:.2f} ms ({chunk_count} chunks)", flush=True)
                
                ws_complete_start = time.perf_counter()
                await websocket.send_text(json.dumps({
                    "type": "sentence_complete"
                }))
                ws_complete_time = self._ms(ws_complete_start)
                total_websocket_time += ws_complete_time
                print(f"   ⏱️  Sentence complete signal: {ws_complete_time:.2f} ms", flush=True)
                
            except Exception as e:
                print(f"   ❌ Final TTS error: {e}", flush=True)
        
        flush_time = self._ms(flush_start)

        # 6️⃣ Send completion signal
        completion_start = time.perf_counter()
        await websocket.send_text(json.dumps({
            "type": "done"
        }))
        completion_time = self._ms(completion_start)
        print(f"⏱️  [5. COMPLETION SIGNAL] Sent in: {completion_time:.2f} ms", flush=True)

        # 7️⃣ Background save
        bg_start = time.perf_counter()
        asyncio.create_task(
            asyncio.to_thread(
                SummaryService.persist_messages_and_update_summary,
                session_id=session_id,
                user_text=text,
                assistant_text=full_response,
                model="gpt-4o-mini",
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                user_id=user_id,
                fakeSessionId=fakeSessionId,
            )
        )
        bg_scheduled_time = self._ms(bg_start)
        print(f"⏱️  [6. BACKGROUND TASK] Scheduled in: {bg_scheduled_time:.2f} ms (non-blocking)", flush=True)

        # 🎯 FINAL SUMMARY
        total_time = self._ms(pipeline_start)
        print("\n" + "="*80, flush=True)
        print("📊 [TIMING SUMMARY]", flush=True)
        print("="*80, flush=True)
        print(f"1. Database context:        {context_time:8.2f} ms", flush=True)
        print(f"2. Prompt building:         {prompt_time:8.2f} ms", flush=True)
        print(f"3. LLM initialization:      {llm_init_time:8.2f} ms", flush=True)
        print(f"4. Stream processing:       {stream_time:8.2f} ms", flush=True)
        print(f"   - Total TTS time:        {total_tts_time:8.2f} ms ({(total_tts_time/stream_time*100):.1f}% of stream)", flush=True)
        print(f"   - Total WebSocket time:  {total_websocket_time:8.2f} ms ({(total_websocket_time/stream_time*100):.1f}% of stream)", flush=True)
        print(f"5. Buffer flush:            {flush_time:8.2f} ms", flush=True)
        print(f"6. Completion signal:       {completion_time:8.2f} ms", flush=True)
        print(f"7. Background task:         {bg_scheduled_time:8.2f} ms", flush=True)
        print("-"*80, flush=True)
        print(f"🎯 TOTAL PIPELINE TIME:     {total_time:8.2f} ms ({total_time/1000:.2f} seconds)", flush=True)
        print(f"   Sentences processed:      {sentence_count}", flush=True)
        print(f"   Response length:          {len(full_response)} characters", flush=True)
        print("="*80 + "\n", flush=True)


    async def handle_stream(
        self,
        data: dict,
        user_id: str | None,
        websocket: WebSocket,
    ):
        """
        NEW STREAMING FLOW
        - sessionId via WS text
        - audio via WS bytes
        - no return
        """

        if "text" not in data or not data["text"]:
            return

        payload = json.loads(data["text"])

        # 🛑 control messages
        if payload.get("type") in ("stop", "interrupt"):
            print(f"🛑 {payload.get('type')} received", flush=True)
            return

        text = payload.get("text")
        session_id = payload.get("sessionId")
        fake_session_id = None

        # 🆕 create session
        if not session_id:
            fake_session_id = str(uuid.uuid4())
            session_id = fake_session_id

            # 🔥 send sessionId immediately
            await websocket.send_text(json.dumps({
                "type": "session",
                "sessionId": session_id
            }))

        print(f"🎯 session_id={session_id}", flush=True)

        # 🚀 STREAMING PIPELINE
        await self.process_text_streaming(
            text=text,
            session_id=session_id,
            user_id=user_id,
            websocket=websocket,
            fakeSessionId=fake_session_id,
        )
