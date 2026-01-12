# from fastapi import APIRouter, HTTPException
# from ..routes.doc_extract import process_pdf_extraction

# router = APIRouter()

# @router.post("/run")
# async def extract_from_worker(payload: dict):
#     """
#     Called ONLY by Node worker
#     """
#     try:
#         print("[python-worker] received job", payload["jobId"])

#         content = process_pdf_extraction(
#             user=payload["user"],
#             file_path=payload["filePath"],
#             image_dir=payload["imageDir"],
#             fileName=payload["fileName"]
#         )

#         return {
#             "status": "completed",
#             "content_length": len(content)
#         }

#     except Exception as e:
#         print("[python-worker] failed", str(e))
#         raise HTTPException(500, str(e))
import os
from fastapi import APIRouter, HTTPException
from ..routes.doc_extract import process_pdf_extraction

router = APIRouter()

@router.post("/run")
async def extract_from_worker(payload: dict):
    """
    Called ONLY by Node worker
    """
    try:
        job_id = payload.get("jobId")
        file_path = payload.get("filePath")
        
        print(f"[python-worker] ======================================")
        print(f"[python-worker] 📥 Received job: {job_id}")
        print(f"[python-worker] File path (from payload): {file_path}")
        
        # Ensure the file path exists and is valid
        if not file_path:
            raise ValueError("filePath is required")
        
        # Verify file exists, provide detailed error info
        file_exists = os.path.exists(file_path)
        print(f"[python-worker] File exists: {file_exists}")
        
        if file_exists:
            file_size = os.path.getsize(file_path)
            print(f"[python-worker] File size: {file_size} bytes")
        else:
            # Try to provide helpful debugging info
            dir_path = os.path.dirname(file_path)
            print(f"[python-worker] ❌ File not found at: {file_path}")
            print(f"[python-worker] Directory exists: {os.path.exists(dir_path)}")
            if os.path.exists(dir_path):
                files_in_dir = os.listdir(dir_path)
                print(f"[python-worker] Files in directory (first 5): {files_in_dir[:5]}")
                # Check if file exists with a slight delay (in case of sync issues)
                import time
                time.sleep(0.5)
                if os.path.exists(file_path):
                    print(f"[python-worker] ✅ File found after 0.5s delay!")
                    file_size = os.path.getsize(file_path)
                    print(f"[python-worker] File size: {file_size} bytes")
                else:
                    raise FileNotFoundError(f"File not found after retry: {file_path}")
            else:
                raise FileNotFoundError(f"Directory not found: {dir_path}")
        
        # FIX: Generate imageDir with consistent absolute path
        image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../uploads/images", job_id))
        os.makedirs(image_dir, exist_ok=True)

        print(f"[python-worker] 🔄 Starting extraction...")
        content = await process_pdf_extraction(
            user=payload.get("user", {}), # Use .get() for safety
            file_path=file_path,
            image_dir=image_dir,          # Pass the generated path
            fileName=payload.get("fileName"),
            job_id=job_id,
            batch_id=payload.get("batchId")
        )
        
        print(f"[python-worker] ✅ Extraction completed for {job_id}")

        # Log response size before returning
        # ⚠️ DON'T return full content in HTTP response
        # Content is already saved in database by process_pdf_extraction
        # Returning it causes ECONNRESET on large documents
        response_data = {
            "status": "completed",
            "jobId": job_id,
            "contentLength": len(content),  # Just send size, not content
            "message": "Document extracted and saved successfully"
        }
        print(f"[python-worker] 📄 Content length: {len(content)} characters")
        print(f"[python-worker] ✅ Returning response to Gateway...")

        return response_data

    except FileNotFoundError as e:
        print(f"[python-worker] ❌ FILE NOT FOUND: {str(e)}")
        raise HTTPException(404, f"File not found: {str(e)}")
    except ValueError as e:
        print(f"[python-worker] ❌ VALIDATION ERROR: {str(e)}")
        raise HTTPException(400, f"Invalid request: {str(e)}")
    except Exception as e:
        print(f"[python-worker] ❌ EXTRACTION FAILED: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"{type(e).__name__}: {str(e)}")