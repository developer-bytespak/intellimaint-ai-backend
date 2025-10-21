from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio file"""
    return {"text": ""}

@router.post("/synthesize")
async def synthesize_speech(request: dict):
    """Convert text to speech"""
    return {"audio_url": ""}

