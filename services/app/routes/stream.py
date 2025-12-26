
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stream_service import StreamService
import traceback
import time

router = APIRouter()
DEBUG = True

# @router.websocket("/stream")
# async def websocket_endpoint(websocket: WebSocket):
#     conn_start = time.perf_counter()
#     await websocket.accept()
#     service = StreamService()

#     if DEBUG:
#         elapsed = (time.perf_counter() - conn_start) * 1000
#         print(f"[TIMING] websocket_accept: {elapsed:.2f} ms", flush=True)

#     try:
#         while True:
#             step_start = time.perf_counter()
#             data = await websocket.receive()
#             elapsed = (time.perf_counter() - step_start) * 1000
#             if DEBUG:
#                 print(f"[TIMING] websocket_receive: {elapsed:.2f} ms", flush=True)

#             step_start = time.perf_counter()
#             response = await service.handle_stream(
#                 data,
#                 user_id="ce2b5fc6-e38d-48f4-a31d-8782376f9e43"
#             )
#             elapsed = (time.perf_counter() - step_start) * 1000
#             if DEBUG:
#                 print(f"[TIMING] handle_stream: {elapsed:.2f} ms", flush=True)

#             if response is None:
#                 continue

#             if isinstance(response, bytes):
#                 send_start = time.perf_counter()
#                 await websocket.send_bytes(response)  # Directly send bytes
#                 if DEBUG:
#                     elapsed = (time.perf_counter() - send_start) * 1000
#                     print(f"[TIMING] websocket_send_bytes: {elapsed:.2f} ms", flush=True)
#                 # return  # Return after sending the bytes

#             elif isinstance(response, dict) and "fakeSessionId" in response:
#                 # ✅ Send JSON if fakeSessionId is present
#                 await websocket.send_text(json.dumps(response))  # Send JSON string
#                 if DEBUG:
#                     print(f"[TIMING] websocket_send_text: sent fakeSessionId", flush=True)
#                 # return

#             else:
#                 send_start = time.perf_counter()
#                 await websocket.send_text(str(response))  # Send response as a text message
#                 if DEBUG:
#                     elapsed = (time.perf_counter() - send_start) * 1000
#                     print(f"[TIMING] websocket_send_text: {elapsed:.2f} ms", flush=True)
#                 # return


#     except WebSocketDisconnect:
#         elapsed = (time.perf_counter() - conn_start) * 1000
#         if DEBUG:
#             print(f"[TIMING] websocket_total: {elapsed:.2f} ms", flush=True)
#     except Exception:
#         elapsed = (time.perf_counter() - conn_start) * 1000
#         if DEBUG:
#             print(f"[TIMING] websocket_total: {elapsed:.2f} ms", flush=True)
#         print(traceback.format_exc(), flush=True)
@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    conn_start = time.perf_counter()
    await websocket.accept()
    service = StreamService()

    if DEBUG:
        elapsed = (time.perf_counter() - conn_start) * 1000
        print(f"[TIMING] websocket_accept: {elapsed:.2f} ms", flush=True)

    try:
        while True:
            step_start = time.perf_counter()
            data = await websocket.receive()
            elapsed = (time.perf_counter() - step_start) * 1000
            if DEBUG:
                print(f"[TIMING] websocket_receive: {elapsed:.2f} ms", flush=True)

            step_start = time.perf_counter()
            response = await service.handle_stream(
                data,
                user_id="ce2b5fc6-e38d-48f4-a31d-8782376f9e43"
            )
            elapsed = (time.perf_counter() - step_start) * 1000
            if DEBUG:
                print(f"[TIMING] handle_stream: {elapsed:.2f} ms", flush=True)

            if response is None or response is False:
                continue

            # Check if response is a tuple (audio_bytes, fake_session_id)
            if isinstance(response, tuple) and len(response) == 2:
                audio_bytes, fake_session_id = response
                
                # First send the fakeSessionId as JSON
                send_start = time.perf_counter()
                await websocket.send_text(json.dumps({"fakeSessionId": fake_session_id}))
                if DEBUG:
                    elapsed = (time.perf_counter() - send_start) * 1000
                    print(f"[TIMING] websocket_send_text (fakeSessionId): {elapsed:.2f} ms", flush=True)
                
                # Then send the audio bytes
                send_start = time.perf_counter()
                await websocket.send_bytes(audio_bytes)
                if DEBUG:
                    elapsed = (time.perf_counter() - send_start) * 1000
                    print(f"[TIMING] websocket_send_bytes: {elapsed:.2f} ms", flush=True)

            elif isinstance(response, bytes):
                send_start = time.perf_counter()
                await websocket.send_bytes(response)
                if DEBUG:
                    elapsed = (time.perf_counter() - send_start) * 1000
                    print(f"[TIMING] websocket_send_bytes: {elapsed:.2f} ms", flush=True)

            elif isinstance(response, dict):
                await websocket.send_text(json.dumps(response))
                if DEBUG:
                    print(f"[TIMING] websocket_send_text: sent dict", flush=True)

            else:
                send_start = time.perf_counter()
                await websocket.send_text(str(response))
                if DEBUG:
                    elapsed = (time.perf_counter() - send_start) * 1000
                    print(f"[TIMING] websocket_send_text: {elapsed:.2f} ms", flush=True)

    except WebSocketDisconnect:
        elapsed = (time.perf_counter() - conn_start) * 1000
        if DEBUG:
            print(f"[TIMING] websocket_total: {elapsed:.2f} ms", flush=True)
    except Exception:
        elapsed = (time.perf_counter() - conn_start) * 1000
        if DEBUG:
            print(f"[TIMING] websocket_total: {elapsed:.2f} ms", flush=True)
        print(traceback.format_exc(), flush=True)