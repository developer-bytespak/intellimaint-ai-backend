import json
import os
import time
import uuid
import asyncio
from openai import AsyncOpenAI


class StreamService:

    def __init__(self):

        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        self.system_instruction = """
You are a helpful technical assistant.
Speak clearly.
Use short sentences.
"""


    # ---------------- MAIN ----------------

    async def process_stream(
        self,
        user_text: str,
        websocket,
        session_id: str | None = None,
    ):

        if not user_text:
            return


        # Create session if missing
        if not session_id:
            session_id = str(uuid.uuid4())

            await websocket.send_text(json.dumps({
                "type": "session",
                "sessionId": session_id
            }))


        print("🎯 Session:", session_id, flush=True)


        # ---------------- LLM STREAM ----------------

        stream = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            stream=True,
            messages=[
                {
                    "role": "system",
                    "content": self.system_instruction
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            temperature=0.3,
        )


        buffer = ""


        async for event in stream:

            delta = event.choices[0].delta.content

            if not delta:
                continue


            buffer += delta


            # Sentence flush rule
            if self._should_flush(buffer):

                sentence = buffer.strip()
                buffer = ""

                if sentence:

                    await websocket.send_text(json.dumps({
                        "type": "text",
                        "content": sentence
                    }))


        # Flush remaining
        if buffer.strip():

            await websocket.send_text(json.dumps({
                "type": "text",
                "content": buffer.strip()
            }))


        # Done signal
        await websocket.send_text(json.dumps({
            "type": "done"
        }))


        print("✅ LLM stream done", flush=True)



    # ---------------- HELPERS ----------------

    def _should_flush(self, buf: str) -> bool:

        MAX_WORDS = 8
        MAX_CHARS = 120

        if any(buf.endswith(x) for x in (".", "?", "!", "\n")):
            return True

        if len(buf.split()) >= MAX_WORDS:
            return True

        if len(buf) >= MAX_CHARS:
            return True

        return False



    # ---------------- WS ENTRY ----------------

    async def handle_stream(
        self,
        data: dict,
        websocket,
    ):

        payload = json.loads(data["text"])

        # Stop / interrupt
        if payload.get("type") in ("stop", "interrupt"):
            return


        user_text = payload.get("text")
        session_id = payload.get("sessionId")


        await self.process_stream(
            user_text=user_text,
            websocket=websocket,
            session_id=session_id,
        )
