from fastapi import APIRouter, UploadFile, File, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any
from ..services.asr_tts_service import transcribe_audio, synthesize_speech
import io
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SynthesizeRequest(BaseModel):
    """Request model for text-to-speech"""
    text: str


class TranscribeResponse(BaseModel):
    """Response model for transcription"""
    status: int
    message: str
    data: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
    try:
        # Read the uploaded file content
        audio_bytes = await file.read()
        
        # Get the content type from the uploaded file
        mimetype = file.content_type or "audio/wav"
        
        # Transcribe the audio
        transcript = await transcribe_audio(audio_bytes, mimetype)
        response_data = {
            "status": 200,
            "message": "Audio transcribed successfully",
            "data": transcript
        }
        return response_data
        
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
        # # Synthesize speech
        # logger.info(f"TTS request received for text: {request.text[:50]}...")
        # print(f"[ASR/TTS] TTS request received for text: {request.text[:50]}...")
        
        audio_bytes = await synthesize_speech(request.text)
        
        # logger.info(f"TTS response: Generated {len(audio_bytes)} bytes of audio")
        # print(f"[ASR/TTS] TTS response: Generated {len(audio_bytes)} bytes of audio")
        
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

