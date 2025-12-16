from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stream_service import StreamService
import traceback

router = APIRouter()

DEBUG = True  # Set to False in production

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    service = StreamService()
    
    if DEBUG:
        print("\n" + "="*50)
        print("[WebSocket] ✅ Connection accepted")
        print("="*50 + "\n")

    try:
        while True:
            if DEBUG:
                print("[WebSocket] ⏳ Waiting for data...")
            
            data = await websocket.receive()
            
            if DEBUG:
                print(f"[WebSocket] 📨 RECEIVED → Keys: {list(data.keys())}")
                
                # Log data sizes
                if "bytes" in data:
                    print(f"[WebSocket] 📦 Audio bytes: {len(data['bytes'])} bytes")
                if "text" in data:
                    print(f"[WebSocket] 📝 Text message: {data['text'][:100]}")

            # ✅ Process incoming data
            response = await service.handle_stream(data)

            # ✅ Send response if generated
            if response is not None:
                if isinstance(response, bytes):
                    if DEBUG:
                        print(f"[WebSocket] 📤 Sending AUDIO → {len(response)} bytes")
                    await websocket.send_bytes(response)
                    if DEBUG:
                        print("[WebSocket] ✅ Audio sent successfully")
                        
                else:
                    if DEBUG:
                        print(f"[WebSocket] 📤 Sending TEXT → {response}")
                    await websocket.send_text(str(response))
                    if DEBUG:
                        print("[WebSocket] ✅ Text sent successfully")

    except WebSocketDisconnect:
        if DEBUG:
            print("\n" + "="*50)
            print("[WebSocket] 🔌 Client disconnected gracefully")
            print("="*50 + "\n")

    except Exception as e:
        print("\n" + "="*50)
        print("[WebSocket] ❌ ERROR occurred:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("\nFull traceback:")
        print(traceback.format_exc())
        print("="*50 + "\n")
        
        # ✅ Try to send error message to client
        try:
            error_msg = {
                "type": "error",
                "message": str(e),
                "error_type": type(e).__name__
            }
            await websocket.send_text(str(error_msg))
        except:
            pass  # Client might already be disconnected

    finally:
        if DEBUG:
            print("\n" + "="*50)
            print("[WebSocket] 🏁 Connection closed - cleanup complete")
            print("="*50 + "\n")