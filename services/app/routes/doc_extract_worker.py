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
        print("[python-worker] received job", payload["jobId"])
        
        # FIX: Generate imageDir here, since Gateway doesn't send it
        image_dir = os.path.join("uploads", "images", payload["jobId"])
        os.makedirs(image_dir, exist_ok=True)

        content = await process_pdf_extraction(
            user=payload.get("user", {}), # Use .get() for safety
            file_path=payload["filePath"],
            image_dir=image_dir,          # Pass the generated path
            fileName=payload["fileName"],
            job_id=payload.get("jobId"),
            batch_id=payload.get("batchId")
        )

        return {
            "status": "completed",
            "content": content,
            "content_length": len(content)
        }

    except Exception as e:
        print("[python-worker] failed", str(e))
        raise HTTPException(500, str(e))