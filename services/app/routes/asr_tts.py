from fastapi import APIRouter, UploadFile, File, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ..services.asr_tts_service import transcribe_audio, synthesize_speech
import io

router = APIRouter()


class SynthesizeRequest(BaseModel):
    """Request model for text-to-speech"""
    text: str


@router.post("/transcribe")
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
   
    if not file:
        raise HTTPException(status_code=400, detail="No audio file uploaded")
    
    try:
        # Read audio file content
        audio_content = await file.read()
        
        # Get mimetype from uploaded file
        mimetype = file.content_type or "audio/wav"
        
        # Transcribe audio
        transcript = await transcribe_audio(audio_content, mimetype)
        
        return {
            "status": 200,
            "message": "Audio transcribed successfully",
            "data": transcript
        }
    except ValueError as e:
        # Configuration error (missing API key)
        if "DEEPGRAM_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/synthesize")
async def synthesize_speech_endpoint(request: SynthesizeRequest):
  
    if not request.text:
        raise HTTPException(status_code=400, detail="Text field is required")
    
    try:
        # Synthesize speech
        audio_bytes = await synthesize_speech(request.text)
        
        # Return audio as binary response
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=synthesized_audio.wav"
            }
        )
    except ValueError as e:
        # Configuration error (missing API key)
        if "DEEPGRAM_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")

