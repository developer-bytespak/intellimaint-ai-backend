

import json
import os
import jwt
import time
import traceback
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from app.services.stream_service import StreamService

router = APIRouter()
DEBUG = True
JWT_SECRET = os.getenv("JWT_SECRET")
# app/routes/stream.py

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    user_id = None

    try:
        # 🔐 auth
        ticket = websocket.query_params.get("ticket")
        decoded = jwt.decode(ticket, JWT_SECRET, algorithms=["HS256"])
        user_id = decoded.get("userId")

        await websocket.accept()
        service = StreamService()

        print(f"🔌 WS connected user={user_id}")

        while True:
            data = await websocket.receive()

            if data.get("type") == "websocket.disconnect":
                break

            # 🚀 NEW FLOW: service sends everything itself
            await service.handle_stream(
                data=data,
                user_id=user_id,
                websocket=websocket
            )

    except WebSocketDisconnect:
        print("ℹ️ WS disconnected")

    finally:
        print(f"🔌 WS closed user={user_id}")
