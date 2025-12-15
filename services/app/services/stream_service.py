import json
from app.services.asr_tts_service import synthesize_speech

DEBUG = True


class StreamService:
    def __init__(self):
        self.is_processing = False
        self.should_cancel = False

        if DEBUG:
            print("[Stream] ✅ Service initialized")

    # -----------------------------
    # LLM + TTS
    # -----------------------------
    async def call_llm(self, text: str) -> str:
        # 🔁 Replace with real LLM
        return f"I heard: {text}"

    async def text_to_audio(self, text: str) -> bytes:
        return await synthesize_speech(text)

    async def process_text(self, text: str) -> bytes | None:
        if self.is_processing:
            if DEBUG:
                print("[Process] ⏳ Already processing")
            return None

        self.is_processing = True
        self.should_cancel = False
        try:
            text = text.strip()
            if not text:
                return None

            if DEBUG:
                print(f"[Process] 🧠 LLM input: {text}")

            # 🧠 LLM
            reply = await self.call_llm(text)

            # Check if processing was cancelled
            if self.should_cancel:
                if DEBUG:
                    print("[Process] ⏸️ Processing cancelled by interrupt")
                return None

            if DEBUG:
                print(f"[Process] 🗣️ LLM reply: {reply}")

            # 🔊 TTS
            audio_bytes = await self.text_to_audio(reply)

            # Check again if processing was cancelled before returning
            if self.should_cancel:
                if DEBUG:
                    print("[Process] ⏸️ Audio generation cancelled by interrupt")
                return None

            if DEBUG:
                print(f"[Process] 🔊 Audio generated ({len(audio_bytes)} bytes)")

            return audio_bytes

        finally:
            self.is_processing = False

    # -----------------------------
    # WebSocket interface
    # -----------------------------
    async def handle_stream(self, data: dict):
        # Handle interrupt message
        if "text" in data:
            try:
                msg = json.loads(data["text"])
                if msg.get("type") == "user_interrupt":
                    if DEBUG:
                        print("[StreamService] ⛔ User interrupt received. Resetting process.")
                    self.should_cancel = True
                    return None
            except (json.JSONDecodeError, AttributeError):
                pass

        if "text" not in data or not data["text"]:
            return None

        msg = json.loads(data["text"])

        if msg.get("type") != "final_text":
            return None

        text = msg.get("text", "")
        return await self.process_text(text)
