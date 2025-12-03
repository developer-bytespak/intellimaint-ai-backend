# # from fastapi import APIRouter, File, UploadFile
# # from ..services.voice_agent_services import process_audio


# # router = APIRouter()

# # @router.post("/upload-audio/")
# # async def upload_audio(file: UploadFile = File(...)):
# #     try:
# #         # File ko temporary store karenge
# #         file_location = f"temp_{file.filename}"
# #         with open(file_location, "wb") as f:
# #             f.write(await file.read())
        
# #         # Deepgram ki service ko call karte hain audio file ke liye
# #         transcript = await process_audio(file_location)
        
# #         # Response return karenge
# #         if transcript:
# #             return {"status": "success", "transcript": transcript}
# #         else:
# #             return {"status": "failed", "message": "Audio processing failed"}
# #     except Exception as e:
# #         return {"status": "error", "message": str(e)}



# from fastapi import APIRouter, File, UploadFile
# from fastapi.responses import StreamingResponse
# from ..services.voice_agent_services import process_audio, text_to_speech
# import io

# router = APIRouter()

# @router.post("/upload-audio/")
# async def upload_audio(file: UploadFile = File(...)):
#     try:
#         # File ko temporary store karenge
#         file_location = f"temp_{file.filename}"
#         with open(file_location, "wb") as f:
#             f.write(await file.read())
        
#         # Deepgram ki service ko call karte hain audio file ke liye
#         transcript = await process_audio(file_location)
        
#         if transcript:
#             # Convert the transcript text to speech
#             audio_data = await text_to_speech(transcript)

#             # Return the audio file as a response to be played on the frontend
#             audio_stream = io.BytesIO(audio_data)
#             return StreamingResponse(audio_stream, media_type="audio/mp3")
#         else:
#             return {"status": "failed", "message": "Audio processing failed"}
    
#     except Exception as e:
#         return {"status": "error", "message": str(e)}
