import os
import uuid
import shutil
import fitz
import json

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse

from ..services.doc_extract_service import DocumentService
from ..services.knowledge_store_service import KnowledgeStoreService
from ..redis_client import redis_client

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def process_pdf_extraction(
    user: dict,
    file_path: str, 
    image_dir: str,
    fileName: str = None,
    model_id: str = None,
    user_id: str = None,
    job_id: str = None,
    batch_id: str = None
) -> str:
    
    print(f"Processing PDF extraction for file: {fileName}")

    def update_progress(p: int):
        if job_id and redis_client and batch_id:
            redis_client.hset(f"job:{job_id}", mapping={"progress": str(p), "status": "processing"})
            print(f"Job {job_id} progress updated to {p}%")
            # redis_client.rpush(f"batch:{batch_id}:jobs", job_id)
            redis_client.publish(f"batch-events:{batch_id}", json.dumps({
                "type": "job_updated",
                "jobId": job_id,
                "status": "processing",
                "progress": p,
                "timestamp": int(__import__('time').time() * 1000)
            }))



    try:
        update_progress(10)

        # STEP 1: Text + Images Extraction
        text_with_placeholders, extracted_images = DocumentService.extract_text_with_image_markers(
            file_path, image_dir
        )
        update_progress(30)

        # STEP 2: Table Extraction
        extracted_tables = DocumentService.extract_and_format_tables_from_pdf(
            file_path
        )
        update_progress(50)

        # STEP 3: Image Upload
        image_urls = DocumentService.upload_images_to_supabase(
            extracted_images
        )
        update_progress(70)

        # STEP 4: Unified Content
        text_with_urls = DocumentService.replace_placeholders_with_urls(text_with_placeholders, image_urls)
        unified_content = DocumentService.create_unified_content(text_with_urls, extracted_tables)
        update_progress(90)

        # Background DB Storage
        try:
            print("Attempting to log knowledge source to DB...", fileName)
            KnowledgeStoreService.create_knowledge_source(
                title=fileName or "Untitled Document",
                raw_content=unified_content,
                source_type="pdf",
                model_id=model_id,
                user_id=user.get("userId"),
                email=user.get("email"),
                role=user.get("role"),
                name=user.get("name")
            )
        except Exception as db_err:
            print(f"DB Logging Error (Extraction still succeeds): {db_err}")

        if job_id and redis_client:
            redis_client.hset(f"job:{job_id}", mapping={"progress": "100", "status": "completed"})

        return unified_content

    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        raise e
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(image_dir):
            shutil.rmtree(image_dir)


@router.post("/extract/full")
async def extract_text_and_images(
    userId: str,  # Query param 1
    name: str = None,  # Query param 2 (optional)
    role: str = None,  # Query param 3
    email: str = None,  # Query param 4
    file: UploadFile = File(...)
):
    """Extract text, images, and tables from a PDF."""
    print(f"Extracting text and images from PDF: {file.filename}")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file format. Only PDF files are allowed.")

    # Save PDF temporarily
    temp_name = f"{uuid.uuid4()}.pdf"
    file_path = os.path.join(UPLOAD_DIR, temp_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        # Make sure upload stream is closed (prevents Windows file locking)
        try:
            file.file.close()
        except Exception:
            pass

    # Create temp image folder
    image_dir = os.path.join(UPLOAD_DIR, f"img_{uuid.uuid4()}")
    os.makedirs(image_dir, exist_ok=True)

    user = {
        "userId": userId,
        "name": name,
        "role": role,
        "email": email
    }

    # Process PDF synchronously and return unified content
    try:
        unified_content = process_pdf_extraction(
            user=user,
            file_path=file_path,
            image_dir=image_dir,
            fileName=file.filename
        )
        
        return PlainTextResponse(
            content=unified_content,
            media_type="text/plain"
        )
    except Exception as e:
        # Ensure cleanup happens even if processing fails
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(image_dir):
            shutil.rmtree(image_dir)
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@router.post("/extract/internal")
async def extract_internal(payload: dict):
    """
    INTERNAL USE ONLY
    Called by Node worker
    """
    try:
        file_path = payload["filePath"]
        file_name = payload.get("fileName")
        user = payload.get("user", {})
        job_id = payload.get("jobId")
        batch_id = payload.get("batchId")


        image_dir = os.path.join("uploads", f"img_{uuid.uuid4()}")
        os.makedirs(image_dir, exist_ok=True)

        result = process_pdf_extraction(
            user=user,
            file_path=file_path,
            image_dir=image_dir,
            fileName=file_name,
            # model_id=None,
            # user_id=None,
            job_id=job_id,
            batch_id=batch_id
        )

        return {
            "status": "completed",
            "result": "ok"
        }

    except Exception as e:
        raise HTTPException(500, str(e))


