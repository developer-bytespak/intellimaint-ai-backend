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
        print(f"[python-worker] File path: {file_path}")
        print(f"[python-worker] File exists: {os.path.exists(file_path)}")
        
        if not file_path:
            raise ValueError("filePath is required")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # FIX: Generate imageDir here, since Gateway doesn't send it
        image_dir = os.path.join("uploads", "images", job_id)
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

        return {
            "status": "completed",
            "content": content,
            "content_length": len(content)
        }

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