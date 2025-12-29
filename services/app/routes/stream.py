

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

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    # 1. Ticket extraction from query params
    ticket = websocket.query_params.get("ticket")
    user_id = None

    try:
        if not ticket:
            print("❌ No ticket provided")
            await websocket.close(code=1008, reason="Missing ticket")
            return

        # 2. JWT Verification
        try:
            decoded = jwt.decode(ticket, JWT_SECRET, algorithms=["HS256"])
            user_id = decoded.get("userId")
            if not user_id:
                await websocket.close(code=1008, reason="Invalid user in ticket")
                return
            # if DEBUG:
                # print(f"✅ User authenticated: {user_id}")
        except jwt.ExpiredSignatureError:
            await websocket.close(code=1008, reason="Ticket expired")
            return
        except jwt.InvalidTokenError:
            await websocket.close(code=1008, reason="Invalid ticket")
            return

        # 3. Accept Connection
        conn_start = time.perf_counter()
        await websocket.accept()
        service = StreamService()

        if DEBUG:
            elapsed = (time.perf_counter() - conn_start) * 1000
            print(f"[TIMING] websocket_accept: {elapsed:.2f} ms")

        # 4. Message Loop
        while True:
            try:
                # Receive data
                step_start = time.perf_counter()
                data = await websocket.receive()
                
                # Check if client is disconnecting
                if data.get("type") == "websocket.disconnect":
                    break

                if DEBUG:
                    recv_elapsed = (time.perf_counter() - step_start) * 1000
                    print(f"[TIMING] websocket_receive: {recv_elapsed:.2f} ms")

                # Process data
                proc_start = time.perf_counter()
                response = await service.handle_stream(data, user_id=user_id)
                
                if DEBUG:
                    proc_elapsed = (time.perf_counter() - proc_start) * 1000
                    print(f"[TIMING] handle_stream: {proc_elapsed:.2f} ms")

                if response is None or response is False:
                    continue

                # 5. Handle Responses (Bytes, Dict, Tuple)
                await send_socket_response(websocket, response)

            except WebSocketDisconnect:
                print(f"ℹ️ WebSocket disconnected for user: {user_id}")
                break
            except Exception as e:
                print(f"⚠️ Error processing message: {str(e)}")
                if DEBUG:
                    traceback.print_exc()
                break

    except Exception as e:
        print(f"🚨 Connection error: {str(e)}")
    finally:
        # Cleanup if needed
        print(f"🔌 Connection closed for {user_id}")

async def send_socket_response(websocket: WebSocket, response):
    """Helper function to send different types of data safely"""
    try:
        # Case: Tuple (audio_bytes, fake_session_id)
        if isinstance(response, tuple) and len(response) == 2:
            audio_bytes, fake_session_id = response
            await websocket.send_text(json.dumps({"fakeSessionId": fake_session_id}))
            await websocket.send_bytes(audio_bytes)

        # Case: Pure Bytes
        elif isinstance(response, bytes):
            await websocket.send_bytes(response)

        # Case: Dictionary
        elif isinstance(response, dict):
            await websocket.send_json(response)

        # Case: String or others
        else:
            await websocket.send_text(str(response))
            
    except Exception as e:
        print(f"❌ Failed to send message: {e}")