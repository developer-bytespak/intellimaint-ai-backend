# from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# from app.services.stream_service import StreamService

# router = APIRouter()

# @router.websocket("/stream")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()

#     service = StreamService()   # service ka object

#     while True:
#         try:
#             data = await websocket.receive()

#             response = await service.handle_stream(data)

#             # agar service ne koi response bhejne ko kaha ho
#             if response is not None:
#                 # Check if response is bytes (audio) or string (text)
#                 if isinstance(response, bytes):
#                     # Audio response ko binary format mein bhejo
#                     await websocket.send_bytes(response)
#                 else:
#                     # Text response ko text format mein bhejo
#                     await websocket.send_text(str(response))

#         except WebSocketDisconnect:
#             print("Client disconnected")
#             break

#         except Exception as e:
#             print(f"Error: {e}")
#             await websocket.close(code=1000)
#             break


from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stream_service import StreamService

router = APIRouter()

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    service = StreamService()   # service ka object

    while True:
        try:
            data = await websocket.receive()  # WebSocket se data receive karna

            response = await service.handle_stream(data)  # Audio chunk process karna

            if response is not None:
                # Audio response ko binary format mein bhejo
                print(f"Sending AUDIO response: {len(response)} bytes")
                await websocket.send_bytes(response)

        except WebSocketDisconnect:
            print("Client disconnected")
            break

        except Exception as e:
            print(f"Error: {e}")
            await websocket.close(code=1000)
            break

