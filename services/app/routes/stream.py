# # from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# # from app.services.stream_service import StreamService
# # import traceback

# # router = APIRouter()

# # DEBUG = True  # Set to False in production

# # @router.websocket("/stream")
# # async def websocket_endpoint(websocket: WebSocket):
# #     await websocket.accept()
# #     service = StreamService()
    
# #     if DEBUG:
# #         print("\n" + "="*50)
# #         print("[WebSocket] ✅ Connection accepted")
# #         print("="*50 + "\n")

# #     try:
# #         while True:
# #             if DEBUG:
# #                 print("[WebSocket] ⏳ Waiting for data...")
            
# #             data = await websocket.receive()
            
# #             if DEBUG:
# #                 print(f"[WebSocket] 📨 RECEIVED → Keys: {list(data.keys())}")
                
# #                 # Log data sizes
# #                 if "bytes" in data:
# #                     print(f"[WebSocket] 📦 Audio bytes: {len(data['bytes'])} bytes")
# #                 if "text" in data:
# #                     print(f"[WebSocket] 📝 Text message: {data['text'][:100]}")

# #             # ✅ Process incoming data
# #             response = await service.handle_stream(data, user_id="ce2b5fc6-e38d-48f4-a31d-8782376f9e43")

# #             # ✅ Send response if generated
# #             if response is not None:
# #                 if isinstance(response, bytes):
# #                     if DEBUG:
# #                         print(f"[WebSocket] 📤 Sending AUDIO → {len(response)} bytes")
# #                     await websocket.send_bytes(response)
# #                     if DEBUG:
# #                         print("[WebSocket] ✅ Audio sent successfully")
                        
# #                 else:
# #                     if DEBUG:
# #                         print(f"[WebSocket] 📤 Sending TEXT → {response}")
# #                     await websocket.send_text(str(response))
# #                     if DEBUG:
# #                         print("[WebSocket] ✅ Text sent successfully")

# #     except WebSocketDisconnect:
# #         if DEBUG:
# #             print("\n" + "="*50)
# #             print("[WebSocket] 🔌 Client disconnected gracefully")
# #             print("="*50 + "\n")

# #     except Exception as e:
# #         print("\n" + "="*50)
# #         print("[WebSocket] ❌ ERROR occurred:")
# #         print(f"Error type: {type(e).__name__}")
# #         print(f"Error message: {str(e)}")
# #         print("\nFull traceback:")
# #         print(traceback.format_exc())
# #         print("="*50 + "\n")
        
# #         # ✅ Try to send error message to client
# #         try:
# #             error_msg = {
# #                 "type": "error",
# #                 "message": str(e),
# #                 "error_type": type(e).__name__
# #             }
# #             await websocket.send_text(str(error_msg))
# #         except:
# #             pass  # Client might already be disconnected

# #     finally:
# #         if DEBUG:
# #             print("\n" + "="*50)
# #             print("[WebSocket] 🏁 Connection closed - cleanup complete")
# #             print("="*50 + "\n")

# from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# from app.services.stream_service import StreamService
# import traceback

# router = APIRouter()
# DEBUG = True

# @router.websocket("/stream")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     service = StreamService()

#     if DEBUG:
#         print("[WebSocket] ✅ Connected")

#     try:
#         while True:
#             data = await websocket.receive()

#             try:
#                 response = await service.handle_stream(
#                     data,
#                     user_id="ce2b5fc6-e38d-48f4-a31d-8782376f9e43"
#                 )
#             except Exception:
#                 response = "Sorry, I'm having trouble right now. Please try again in a moment."

#             if response is None:
#                 continue

#             if isinstance(response, bytes):
#                 await websocket.send_bytes(response)
#             else:
#                 await websocket.send_text(str(response))

#     except WebSocketDisconnect:
#         print("[WebSocket] 🔌 Disconnected")

#     except Exception:
#         print(traceback.format_exc())


from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stream_service import StreamService
import traceback
import time

router = APIRouter()
DEBUG = True

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

            if response is None:
                continue

            if isinstance(response, bytes):
                send_start = time.perf_counter()
                await websocket.send_bytes(response)
                if DEBUG:
                    elapsed = (time.perf_counter() - send_start) * 1000
                    print(f"[TIMING] websocket_send_bytes: {elapsed:.2f} ms", flush=True)
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
