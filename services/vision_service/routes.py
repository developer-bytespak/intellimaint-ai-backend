from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/detect")
async def detect_objects(file: UploadFile = File(...)):
    """Detect objects in uploaded image"""
    return {"objects": []}

@router.post("/ocr")
async def extract_text(file: UploadFile = File(...)):
    """Extract text from image"""
    return {"text": ""}

@router.post("/explain")
async def explain_image(file: UploadFile = File(...)):
    """Generate image explanation"""
    return {"explanation": ""}

