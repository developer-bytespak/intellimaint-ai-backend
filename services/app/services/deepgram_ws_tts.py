import aiohttp
import asyncio
import json
import os

DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY")


class DeepgramWSTTS:

    def __init__(self):

        self.url = (
            "wss://api.deepgram.com/v1/speak"
            "?model=aura-asteria-en"
            "&encoding=linear16"
            "&sample_rate=24000"
        )

        self.headers = {
            "Authorization": f"Token {DEEPGRAM_KEY}"
        }

        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.lock = asyncio.Lock()


    async def connect(self):

        if self.ws:
            return

        if not self.session:
            self.session = aiohttp.ClientSession()

        self.ws = await self.session.ws_connect(
            self.url,
            headers=self.headers,
            heartbeat=20,
        )


    async def speak(self, text: str):

        async with self.lock:

            await self.connect()

            await self.ws.send_json({
                "type": "Speak",
                "text": text
            })

            async for msg in self.ws:

                # 🔊 Audio frame
                if msg.type == aiohttp.WSMsgType.BINARY:
                    yield msg.data
                    continue

                # 📝 JSON control
                if msg.type == aiohttp.WSMsgType.TEXT:

                    data = json.loads(msg.data)

                    if data.get("type") == "Flushed":
                        break


    async def close(self):

        if self.ws:
            await self.ws.close()
            self.ws = None

        if self.session:
            await self.session.close()
            self.session = None
