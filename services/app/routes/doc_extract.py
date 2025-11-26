from fastapi import APIRouter, UploadFile, File
from app.services.doc_extract_service import DocumentService
import shutil
import uuid
import os

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/extract/full")
async def extract_text_and_images(file: UploadFile = File(...)):
    """PDF se text + images + tables extract karta hai."""

    # Temporary file save
    temp_name = f"{uuid.uuid4()}.pdf"
    file_path = os.path.join(UPLOAD_DIR, temp_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Prepare image output directory
    image_dir = os.path.join(UPLOAD_DIR, f"img_{uuid.uuid4()}")
    os.makedirs(image_dir, exist_ok=True)

    # Extract text
    raw_text = DocumentService.extract_text_from_pdf(file_path)
    clean_text = raw_text.replace("\u0000", "")
    # clean_text = "\n".join([line for line in clean_text.splitlines() if line.strip()])

    # Extract images
    extracted_images = DocumentService.extract_images_from_pdf(file_path, image_dir)

    # Extract tables
    extracted_tables = DocumentService.extract_tables_from_pdf(file_path)

    # Delete original file
    os.remove(file_path)

    return {
        "filename": file.filename,
        "text": clean_text,
        "total_images": len(extracted_images),
        "images": extracted_images,
        "tables": extracted_tables
    }
