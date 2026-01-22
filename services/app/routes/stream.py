
# app/routes/stream.py
import json
import os
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stream_service import StreamService

router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET")

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    user_id = None

    try:
        # 🔐 Auth (optional for testing)
        ticket = websocket.query_params.get("ticket")
        
        if ticket:
            try:
                decoded = jwt.decode(ticket, JWT_SECRET, algorithms=["HS256"])
                user_id = decoded.get("userId")
            except:
                print("⚠️ Invalid JWT, using dummy user")
                user_id = "test_user_123"  # Dummy for testing
        else:
            user_id = "test_user_123"  # Dummy for testing

        await websocket.accept()
        service = StreamService()

        print(f"🔌 WS connected user={user_id}")

        while True:
            data = await websocket.receive()

            if data.get("type") == "websocket.disconnect":
                break

            # ✅ Fixed: removed user_id parameter
            await service.handle_stream(
                data=data,
                websocket=websocket
            )

    except WebSocketDisconnect:
        print("ℹ️ WS disconnected")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print(f"🔌 WS closed user={user_id}")
