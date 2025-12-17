import os
import uuid
import shutil
import fitz
import asyncio

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse

from ..services.doc_extract_service import DocumentService
from ..services.progress_tracker import ProgressTracker
from ..services.knowledge_store_service import KnowledgeStoreService

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def process_pdf_extraction(
    job_id: str, 
    file_path: str, 
    image_dir: str,
    fileName: str = None, # Isko main identifier banayein
    model_id: str = None,
    user_id: str = None
):
    print(f"Started background PDF extraction for job_id: {fileName}")
    try:
        # STEP 1: Text + Images Extraction
        def update_text_progress(current_page, total_pages):
            ProgressTracker.update_text_extraction_progress(job_id, current_page, total_pages)
        
        text_with_placeholders, extracted_images = DocumentService.extract_text_with_image_markers(
            file_path, image_dir, progress_callback=update_text_progress
        )

        # STEP 2: Table Extraction
        def update_table_progress(current_page, total_pages):
            step_progress = int((current_page / total_pages) * 100) if total_pages > 0 else 0
            ProgressTracker.update_step_progress(job_id, "table_extraction", step_progress)
        
        extracted_tables = DocumentService.extract_and_format_tables_from_pdf(
            file_path, progress_callback=update_table_progress
        )

        # STEP 3: Image Upload
        def update_upload_progress(current_img, total_imgs):
            step_progress = int((current_img / total_imgs) * 100) if total_imgs > 0 else 0
            ProgressTracker.update_step_progress(job_id, "image_upload", step_progress)
        
        image_urls = DocumentService.upload_images_to_supabase(
            extracted_images, progress_callback=update_upload_progress
        )

        # STEP 4: Unified Content
        ProgressTracker.update_step_progress(job_id, "unified_content", 50)
        text_with_urls = DocumentService.replace_placeholders_with_urls(text_with_placeholders, image_urls)
        unified_content = DocumentService.create_unified_content(text_with_urls, extracted_tables)
        ProgressTracker.update_step_progress(job_id, "unified_content", 100)

        # ============================================
        # NEW STEP: Background DB Storage
        # ============================================
        # Hum completion mark karne se pehle save karenge taaki data miss na ho
        try:
            print("Attempting to log knowledge source to DB...",fileName)
            KnowledgeStoreService.create_knowledge_source(
                title=fileName or "Untitled Document",
                raw_content=unified_content,
                source_type="pdf",
                model_id=model_id,
                user_id=user_id
            )
        except Exception as db_err:
            print(f"DB Logging Error (Extraction still succeeds): {db_err}")

        # ============================================
        # Final Mark (Returns Plain Text in GET call)
        # ============================================
        ProgressTracker.mark_completed(job_id, unified_content)

    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        ProgressTracker.mark_failed(job_id, str(e))
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(image_dir):
            shutil.rmtree(image_dir)


@router.post("/extract/full")
async def extract_text_and_images(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Extract text, images, and tables from a PDF with progress tracking."""
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

    # Get total pages first to create job
    try:
        with fitz.open(file_path) as pdf:
            total_pages = len(pdf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading PDF: {str(e)}")

    # Create temp image folder
    image_dir = os.path.join(UPLOAD_DIR, f"img_{uuid.uuid4()}")
    os.makedirs(image_dir, exist_ok=True)

    # Create job and get job_id
    job_id = ProgressTracker.create_job(total_pages=total_pages)

    # Start background processing
    background_tasks.add_task(
    process_pdf_extraction, 
    job_id=job_id, 
    file_path=file_path, 
    image_dir=image_dir,
    fileName=file.filename,  # Named argument use karein
    # model_id=model_id,       # Agar endpoint par receive ho raha hai
    # user_id=user_id          # Agar endpoint par receive ho raha hai
)

    # Return job_id immediately
    return JSONResponse({
        "job_id": job_id,
        "status": "processing",
        "message": "PDF extraction started. Use job_id to check progress.",
        "total_pages": total_pages
    })


@router.get("/extract/progress/{job_id}")
async def get_extraction_progress(job_id: str):
    """
    Get progress of PDF extraction job with long polling at milestones
    Each API call waits until its milestone is reached (25%, 50%, 75%, 100%)
    Returns 200 with progress/data at each milestone
    """
    
    # Maximum wait time: 5 minutes
    MAX_WAIT_TIME = 300  # seconds
    POLL_INTERVAL = 1  # Check every 1 second
    elapsed_time = 0
    
    while elapsed_time < MAX_WAIT_TIME:
        progress = ProgressTracker.get_progress(job_id)
        
        if not progress:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # If completed, return data as plain text
        if progress["status"] == "completed":
            # print(f"Progress: {progress['data']}")
            return PlainTextResponse(
                content=progress["data"],
                media_type="text/plain"
            )
        
        # If failed, return error
        if progress["status"] == "failed":
            return JSONResponse({
                "job_id": job_id,
                "status": "failed",
                "error": progress["error"]
            }, status_code=500)
        
        # Check if we should return progress based on milestone
        should_return, api_call_count = ProgressTracker.check_and_increment_api_call(job_id)
        
        if should_return:
            # Calculate which milestone was reached
            milestone_index = min(api_call_count - 1, len(ProgressTracker.API_MILESTONES) - 1)
            milestone = ProgressTracker.API_MILESTONES[milestone_index] if milestone_index >= 0 else 0
            
            # Return progress info as JSON at milestone
            return JSONResponse({
                "job_id": job_id,
                "status": "processing",
                "progress": progress["progress"],
                "current_step": progress["current_step"],
                "message": progress.get("message", "Processing..."),
                "api_call": api_call_count,
                "milestone": milestone
            })
        
        # Milestone not reached yet, wait and check again
        await asyncio.sleep(POLL_INTERVAL)
        elapsed_time += POLL_INTERVAL
    
    # Timeout - return current progress
    progress = ProgressTracker.get_progress(job_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JSONResponse({
        "job_id": job_id,
        "status": "processing",
        "progress": progress["progress"],
        "current_step": progress["current_step"],
        "message": "Timeout: Job still processing"
    }, status_code=408)
