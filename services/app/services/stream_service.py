import json
import os
import asyncio
import time
from openai import AsyncOpenAI
from app.services.asr_tts_service import synthesize_speech
from app.services.chat_message_service import ChatMessageService
from app.services.summary_service import SummaryService


class StreamService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.system_instruction = (
            "You are a voice assistant. "
            "Short, direct answers. "
            "Plain text only."
        )

    # ---------- helpers ----------
    def _ms(self, start): 
        return (time.perf_counter() - start) * 1000

    # ---------- LLM ----------
    async def call_llm(self, prompt: str):
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
            )
        )

    # ---------- REALTIME ----------
    async def process_text(self, text, session_id, user_id):
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
            parts.append(f"Conversation summary:\n{summary}")
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
        )
        print(
            f"[TIMING] background_task_scheduling: {self._ms(step_start):.2f} ms",
            flush=True,
        )

        print(f"[TIMING] process_text_total: {self._ms(t0):.2f} ms", flush=True)
        return audio

    async def handle_stream(self, data: dict, user_id: str | None):
        if "text" not in data:
            return None

        step_start = time.perf_counter()
        msg = json.loads(data["text"])
        print(f"[TIMING] json_loads: {self._ms(step_start):.2f} ms", flush=True)
        if msg.get("type") != "final_text":
            return None

        step_start = time.perf_counter()
        result = await self.process_text(
            msg.get("text", ""),
            msg.get("sessionId"),
            user_id,
        )
        print(f"[TIMING] process_text: {self._ms(step_start):.2f} ms", flush=True)
        return result



# import json
# import os
# import asyncio
# from openai import AsyncOpenAI
# from app.services.asr_tts_service import synthesize_speech
# from app.services.chat_message_service import ChatMessageService
# from app.services.summary_service import SummaryService
# from app.redis_client import redis_client

# class StreamService:
#     def __init__(self):
#         self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#         self.system_instruction = (
#             "You are a voice assistant. "
#             "Short, direct answers. "
#             "Plain text only."
#         )

#     async def call_llm(self, prompt: str):
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

#     def _schedule_background(self, session_id):
#         asyncio.create_task(
#             asyncio.to_thread(
#                 SummaryService.update_summary_if_needed,
#                 session_id,
#             )
#         )

#     async def process_text(self, text, session_id, user_id):
#         if not text:
#             return None

#         # ---------- REDIS FAST READ ----------
#         last_messages = None
#         summary = None

#         if redis_client and session_id:
#             last_messages = redis_client.get(f"chat:{session_id}:last5")
#             summary = redis_client.get(f"chat:{session_id}:summary")

#             if last_messages:
#                 last_messages = json.loads(last_messages)

#         if last_messages is None:
#             last_messages = ChatMessageService.get_last_messages(session_id, limit=5)
#             if redis_client and session_id:
#                 redis_client.setex(
#                     f"chat:{session_id}:last5",
#                     120,
#                     json.dumps(last_messages),
#                 )

#         if summary is None:
#             summary = ChatMessageService.get_summary(session_id)
#             if redis_client and summary:
#                 redis_client.setex(
#                     f"chat:{session_id}:summary",
#                     120,
#                     summary,
#                 )

#         # ---------- PROMPT ----------
#         parts = []
#         if summary:
#             parts.append(f"Conversation summary:\n{summary}")
#         for m in last_messages:
#             parts.append(f"{m['role']}: {m['content']}")
#         parts.append(f"user: {text}")
#         prompt = "\n".join(parts)

#         # ---------- LLM ----------
#         reply, usage = await self.call_llm(prompt)
#         reply = reply or "Sorry, I could not respond."

#         # ---------- TTS ----------
#         audio = await self.text_to_audio(reply)

#         # ---------- BACKGROUND SAVE ----------
#         ChatMessageService.save_chat_message(session_id, "user", text)
#         ChatMessageService.save_chat_message(
#             session_id,
#             "assistant",
#             reply,
#             model="gpt-4o-mini",
#             prompt_tokens=usage.prompt_tokens if usage else None,
#             completion_tokens=usage.completion_tokens if usage else None,
#             total_tokens=usage.total_tokens if usage else None,
#         )

#         # ---------- REDIS UPDATE ----------
#         if redis_client and session_id:
#             new_last = (last_messages + [
#                 {"role": "user", "content": text},
#                 {"role": "assistant", "content": reply},
#             ])[-5:]

#             redis_client.setex(
#                 f"chat:{session_id}:last5",
#                 120,
#                 json.dumps(new_last),
#             )

#         self._schedule_background(session_id)

#         return audio

#     async def handle_stream(self, data: dict, user_id: str | None):
#         if "text" not in data:
#             return None

#         msg = json.loads(data["text"])
#         if msg.get("type") != "final_text":
#             return None

#         return await self.process_text(
#             msg.get("text", ""),
#             msg.get("sessionId"),
#             user_id,
#         )
