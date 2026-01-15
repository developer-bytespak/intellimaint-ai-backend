import json
import os
import asyncio
import time
import uuid
from openai import AsyncOpenAI
from app.services.asr_tts_service import synthesize_speech
from app.services.chat_message_service import ChatMessageService
from app.services.summary_service import SummaryService
from app.redis_client import redis_client
import uuid


class StreamService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.system_instruction = (
            "You are a helpful voice assistant with access to conversation history. "
            "The context includes:\n"
            "1. A conversation summary (older context)\n"
            "2. Recent messages (latest exchanges)\n\n"
            "When users ask about previous conversations:\n"
            "- Check recent messages first for specific details\n"
            "- Use summary for older context if needed\n"
            "- Be specific about what was discussed\n"
            "- If you can't find what they're asking about, say so clearly\n\n"
            "Keep responses short and natural for voice interaction.\n"
            "Assume the provided summary and recent messages are complete and accurate.\n"
            "Never say you lack access to conversation history unless explicitly stated.\n"
            
        )

        self.redis_client = redis_client

    # ---------- helpers ----------
    def _ms(self, start): 
        return (time.perf_counter() - start) * 1000

    # ---------- LLM ----------
    async def call_llm(self, prompt: str):
        print(f"[LLM Prompt]: {prompt}", flush=True)
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

    # For Create new Session + new ChatMessage records

    

    # ---------- REALTIME ----------
    async def process_text(self, text, session_id, user_id, fakeSessionId):
        t0 = time.perf_counter()
        if not text:
            return None
        

        # 1️⃣ Context read (fast)
        step_start = time.perf_counter()
        last_messages = ChatMessageService.get_last_messages(session_id, 5)
        summary = ChatMessageService.get_summary(session_id)
        print(f"[TIMING] db_context_read: {self._ms(step_start):.2f} ms", flush=True)

        # 2️⃣ Prompt build
        step_start = time.perf_counter()
        parts = []
        if summary:
            parts.append(
            "SYSTEM CONTEXT:\n"
            "The following is an accurate summary of the user's past conversation.\n"
            "You DO have access to this information and should use it as the source of truth.\n\n"
            f"{summary}"
                )
        parts.append(
            "\nThe messages below are the most recent exchanges in THIS session:\n"
        )
        for m in last_messages:
            parts.append(f"{m['role']}: {m['content']}")
        parts.append(f"user: {text}")
        prompt = "\n".join(parts)
        print(f"[TIMING] prompt_build: {self._ms(step_start):.2f} ms", flush=True)

        # 3️⃣ LLM
        try:
            step_start = time.perf_counter()
            reply, usage = await self.call_llm(prompt)
            print(f"[TIMING] llm_call: {self._ms(step_start):.2f} ms", flush=True)
            print(f"[LLM Reply]: {reply}", flush=True)
        except Exception:
            return await self._safe_error_reply()

        # 4️⃣ TTS
        try:
            step_start = time.perf_counter()
            audio = await self.text_to_audio(reply)
            print(f"[TIMING] tts_call: {self._ms(step_start):.2f} ms", flush=True)
        except Exception:
            return await self._safe_error_reply()

        # 5️⃣ BACKGROUND DB + SUMMARY (NON-BLOCKING)
        step_start = time.perf_counter()
        self._schedule_background(
            session_id=session_id,
            user_text=text,
            assistant_text=reply,
            model="gpt-4o-mini",
            usage=usage,
            fakeSessionId=fakeSessionId,
            user_id=user_id,
        )
        print(
            f"[TIMING] background_task_scheduling: {self._ms(step_start):.2f} ms",
            flush=True,
        )

        print(f"[TIMING] process_text_total: {self._ms(t0):.2f} ms", flush=True)
        return audio

    async def handle_stream(self, data: dict, user_id: str | None):
        msg = data

        print(f"[stream_service] handle_stream: received message: {msg}", flush=True)

        if "text" not in msg or not msg["text"]:
            return await self._safe_error_reply() 
    
        if "text" in msg and msg["text"]:
            payload = json.loads(msg["text"])   # 👈 important
            if payload.get("type") == "stop":
                print("[stream_service] handle_stream: received 'stop' message, returning.", flush=True)
                return False
                        # ✅ Handle interrupt message - just return False, no fake_session_id needed
            if payload.get("type") == "interrupt":
                print("[stream_service] handle_stream: received 'interrupt' message, returning.", flush=True)
                return False
        session_id = payload.get("sessionId")
        fake_session_id = None
        if not session_id:
            fake_session_id = str(uuid.uuid4())

        print(f"[stream_service] handle_stream: session_id={session_id}", flush=True)
        print(f"fake_session_id={fake_session_id}", flush=True)

        # return False

        result = await self.process_text(
            payload.get("text", ""),
            session_id,
            user_id,
            fake_session_id
        )
        # If a fake session was generated, return it separately
        if fake_session_id:
            # Return both the result and fake_session_id as a tuple
            return (result, fake_session_id)
        
        return result
       