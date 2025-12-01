# import os
# import uuid
# import shutil
# from fastapi import APIRouter, UploadFile, File, HTTPException
# from fastapi.responses import PlainTextResponse  # IMPORTANT

# from ..services.doc_extract_service import DocumentService

# router = APIRouter()

# UPLOAD_DIR = "uploads"
# os.makedirs(UPLOAD_DIR, exist_ok=True)


# @router.post("/extract/full", response_class=PlainTextResponse)
# async def extract_text_and_images(file: UploadFile = File(...)):
#     """Extract text, images, and tables from a PDF with real spacing."""

#     if not file.filename.lower().endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="Invalid file format. Only PDF files are allowed.")

#     # Save PDF temporarily
#     temp_name = f"{uuid.uuid4()}.pdf"
#     file_path = os.path.join(UPLOAD_DIR, temp_name)

#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     # Create temp image folder
#     image_dir = os.path.join(UPLOAD_DIR, f"img_{uuid.uuid4()}")
#     os.makedirs(image_dir, exist_ok=True)

#     try:
#         # Extract text + markers
#         text_with_placeholders, extracted_images = DocumentService.extract_text_with_image_markers(
#             file_path, image_dir
#         )

#         # Extract tables
#         extracted_tables = DocumentService.extract_and_format_tables_from_pdf(file_path)

#         # Upload images
#         image_urls = DocumentService.upload_images_to_supabase(extracted_images)

#         # Replace markers with real URLs
#         text_with_urls = DocumentService.replace_placeholders_with_urls(text_with_placeholders, image_urls)

#         # Build final text output (with REAL newlines)
#         unified_content = DocumentService.create_unified_content(text_with_urls, extracted_tables)

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

#     finally:
#         # Cleanup
#         if os.path.exists(file_path):
#             os.remove(file_path)
#         if os.path.exists(image_dir):
#             shutil.rmtree(image_dir)

#     # 🔥 RETURN PLAIN TEXT — NOT JSON
#     return PlainTextResponse(
#         content=unified_content,
#         media_type="text/plain"
#     )
import os
import uuid
import shutil

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse

from ..services.doc_extract_service import DocumentService

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/extract/full", response_class=PlainTextResponse)
async def extract_text_and_images(file: UploadFile = File(...)):
    """Extract text, images, and tables from a PDF with real spacing."""

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

    try:
        # Extract text + markers
        text_with_placeholders, extracted_images = DocumentService.extract_text_with_image_markers(
            file_path, image_dir
        )

        # Extract tables
        extracted_tables = DocumentService.extract_and_format_tables_from_pdf(file_path)

        # Upload images
        image_urls = DocumentService.upload_images_to_supabase(extracted_images)

        # Replace markers with real URLs
        text_with_urls = DocumentService.replace_placeholders_with_urls(text_with_placeholders, image_urls)

        # Build final text output
        unified_content = DocumentService.create_unified_content(text_with_urls, extracted_tables)

    except HTTPException:
        # let already-raised HTTPExceptions pass through
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        # Cleanup – wrap deletes to avoid crashing if file is locked
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except PermissionError:
                # On rare cases, Windows may still hold a lock; log instead of crashing
                print(f"Could not delete file {file_path} due to PermissionError.")
        if os.path.exists(image_dir):
            try:
                print(f"Attempting to delete image dir {image_dir}.")
                # shutil.rmtree(image_dir)
            except PermissionError:
                print(f"Could not delete image dir {image_dir} due to PermissionError.")

    # Return plain text
    return PlainTextResponse(
        content=unified_content,
        media_type="text/plain"
    )
