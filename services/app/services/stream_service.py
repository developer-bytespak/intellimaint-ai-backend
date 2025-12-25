# import json
# import os
# from app.services.asr_tts_service import synthesize_speech
# from app.services.chat_message_service import ChatMessageService
# from google import generativeai as genai

# DEBUG = True


# class StreamService:
#     def __init__(self):
#         self.is_processing = False

#         api_key = os.getenv("GEMINI_API_KEY")
#         genai.configure(api_key=api_key)

#         system_instruction = """
#         You are a voice assistant.
#         - Provide short, concise, and direct answers.
#         - Do NOT provide code snippets, markdown, or technical explanations.
#         - Use plain text only.
#         - If asked "Can you hear me?", reply "Yes, I can hear you."
#         - Keep responses under 2-3 sentences.
#         """

#         self.model = genai.GenerativeModel(
#             "gemini-2.5-flash",
#             system_instruction=system_instruction
#         )

#         if DEBUG:
#             print("[Stream] ✅ Service initialized with Gemini")

#     # -----------------------------
#     # LLM Call
#     # -----------------------------
#     async def call_llm(self, text: str):
#         response = await self.model.generate_content_async(text)
#         return response

#     async def text_to_audio(self, text: str) -> bytes:
#         return await synthesize_speech(text)

#     # -----------------------------
#     # Main Processing
#     # -----------------------------
#     async def process_text(self, text: str, session_id: str | None, user_id: str):
#         if self.is_processing:
#             return None

#         self.is_processing = True
#         try:
#             text = text.strip()
#             if not text:
#                 return None

#             # 1️⃣ Create session if first message
#             if not session_id:
#                 result = ChatMessageService.create_chat_session(
#                     user_id=user_id,
#                     title=text
#                 )
#                 session_id = result["session_id"]
#                 print(f"[ChatSession] 🆕 Created session: {session_id}")

#             # 2️⃣ Save USER message
#             ChatMessageService.save_chat_message(
#                 session_id=session_id,
#                 role="user",
#                 content=text
#             )

#             # 3️⃣ Call LLM
#             response = await self.call_llm(text)
#             reply = response.text or "Sorry, I could not respond."

#             # 4️⃣ Extract tokens
#             usage = getattr(response, "usage_metadata", None)
#             prompt_tokens = getattr(usage, "prompt_token_count", None)
#             completion_tokens = getattr(usage, "candidates_token_count", None)
#             total_tokens = getattr(usage, "total_token_count", None)

#             # 5️⃣ Save ASSISTANT message
#             ChatMessageService.save_chat_message(
#                 session_id=session_id,
#                 role="assistant",
#                 content=reply,
#                 model="gemini-2.5-flash",
#                 prompt_tokens=prompt_tokens,
#                 completion_tokens=completion_tokens,
#                 total_tokens=total_tokens
#             )

#             # 6️⃣ TTS
#             return await self.text_to_audio(reply)

#         finally:
#             self.is_processing = False

#     # -----------------------------
#     # WebSocket Handler
#     # -----------------------------
#     async def handle_stream(self, data: dict, user_id: str|None):
#         if "text" not in data:
#             return None

#         msg = json.loads(data["text"])

#         if msg.get("type") != "final_text":
#             return None

#         text = msg.get("text", "")
#         session_id = msg.get("sessionId")  # frontend se aa sakta hai
#         print(f"[Stream] 📝 Received  session_id: {session_id}")

#         return await self.process_text(text, session_id, user_id)
import json
import os
import asyncio
from google import generativeai as genai
from app.services.asr_tts_service import synthesize_speech
from app.services.chat_message_service import ChatMessageService

DEBUG = False


class StreamService:
    def __init__(self):
        self.is_processing = False

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

        system_instruction = """
        You are a voice assistant.
        - Provide short, concise answers.
        - No code or technical explanations.
        - Plain text only.
        """

        self.model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=system_instruction
        )

    # -----------------------------
    # LLM
    # -----------------------------
    async def call_llm(self, text: str):
        response = await self.model.generate_content_async(text)
        if DEBUG:
            print("[LLM] ✅ Response received")
        return response
         


    async def text_to_audio(self, text: str) -> bytes:
        return await synthesize_speech(text)

    async def _safe_error_reply(self) -> bytes | str:
        """Best-effort user-facing error reply.

        Prefer returning TTS audio bytes; fall back to text if TTS fails.
        """
        error_text = "Sorry, I'm having trouble right now. Please try again in a moment."
        try:
            return await self.text_to_audio(error_text)
        except Exception:
            return error_text

    # -----------------------------
    # DB (BLOCKING → THREAD)
    # -----------------------------
    @staticmethod
    def _persist_sync(
        *,
        session_id,
        user_id,
        user_text,
        assistant_text,
        model,
        prompt_tokens,
        completion_tokens,
        total_tokens,
    ):
        try:
            if not session_id:
                created = ChatMessageService.create_chat_session(
                    user_id=user_id,
                    title=user_text[:120]
                )
                if not created:
                    return
                session_id = created["session_id"]

            ChatMessageService.save_chat_message(
                session_id=session_id,
                role="user",
                content=user_text
            )

            ChatMessageService.save_chat_message(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )
        except Exception:
            pass  # Silent fail (voice UX first)

    def _schedule_persist(self, **kwargs):
        task = asyncio.create_task(asyncio.to_thread(StreamService._persist_sync, **kwargs))

        def _swallow(t: asyncio.Task) -> None:
            try:
                t.exception()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        task.add_done_callback(_swallow)

    # -----------------------------
    # REALTIME PATH
    # -----------------------------
    async def process_text(self, text, session_id, user_id):
        if self.is_processing:
            return None

        self.is_processing = True
        try:
            text = (text or "").strip()
            if not text:
                return None

            # 1) LLM (may fail: quota/network/etc)
            try:
                response = await self.call_llm(text)
                reply = getattr(response, "text", None) or "Sorry, I could not respond."
                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = getattr(usage, "prompt_token_count", None)
                completion_tokens = getattr(usage, "candidates_token_count", None)
                total_tokens = getattr(usage, "total_token_count", None)
            except Exception:
                # Never persist on errors
                return await self._safe_error_reply()

            # 2) TTS (may fail)
            try:
                audio = await self.text_to_audio(reply)
            except Exception:
                # Never persist on errors
                return await self._safe_error_reply()

            # 3) Background DB save (non-blocking) only after success
            if user_id:
                self._schedule_persist(
                    session_id=session_id,
                    user_id=user_id,
                    user_text=text,
                    assistant_text=reply,
                    model="gemini-2.5-flash",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )

            return audio

        finally:
            self.is_processing = False
    # -----------------------------
    # WS ENTRY
    # -----------------------------
    async def handle_stream(self, data: dict, user_id: str | None):
        try:
            if "text" not in data:
                return None

            msg = json.loads(data["text"])
            if msg.get("type") != "final_text":
                return None

            return await self.process_text(
                msg.get("text", ""),
                msg.get("sessionId"),
                user_id
            )
        except Exception:
            # Never crash websocket loop
            return await self._safe_error_reply()
