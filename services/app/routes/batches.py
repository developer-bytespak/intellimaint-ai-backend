# import uuid
# import shutil
# from typing import List
# from fastapi import APIRouter, UploadFile, File, HTTPException
# from fastapi.responses import JSONResponse
# from app.services.batch_service import create_batch
# from app.redis_client import redis_client

# router = APIRouter(prefix="/batches", tags=["Batches"])


import uuid
import shutil
import os
import json
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from app.services.batch_service import create_batch
from app.redis_client import redis_client
import asyncio
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/batches", tags=["Batches"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload-pdfs")
async def upload_pdfs(files: List[UploadFile] = File(...),userId:str=Form(...)):
    if not files:
        raise HTTPException(400, "No files uploaded")

    file_info = []

    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Invalid file type: {f.filename}")
        
        # Save file to disk
        file_path = os.path.join(UPLOAD_DIR, f.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)
            
        file_info.append({
            "name": f.filename,
            "path": os.path.abspath(file_path)
        })

    batch_id, jobs = create_batch(file_info,userId)

    return JSONResponse({
        "batchId": batch_id,
        "status": "queued",
        "jobs": jobs
    })


@router.get("/{batch_id}")
def get_batch_status(batch_id: str):
    if not redis_client:
        raise HTTPException(503, "Redis unavailable")

    job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)
    if not job_ids:
        raise HTTPException(404, "Batch not found")

    jobs = []
    for job_id in job_ids:
        data = redis_client.hgetall(f"job:{job_id}")
        jobs.append({
            "jobId": job_id,
            "fileName": data.get("fileName"),
            "status": data.get("status"),
            "progress": data.get("progress"),
            "error": data.get("error")
        })

    return {
        "batchId": batch_id,
        "jobs": jobs
    }




@router.get("/events/{batch_id}")
async def batch_events(batch_id: str):
    async def event_generator():
        last_snapshot = None

        while True:
            job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)

            snapshot = []
            for job_id in job_ids:
                 # FIX: Fetch data and inject jobId manually
                  # FIX: Fetch data and inject jobId manually
                job_data = redis_client.hgetall(f"job:{job_id}")
                job_data["jobId"] = job_id 
                snapshot.append(job_data) # <--- CHANGED: Append the modified job_data, not the raw fetch

            if snapshot != last_snapshot:
                yield {
                    "event": "batch_update",
                    "data": json.dumps(snapshot)
                }
                last_snapshot = snapshot

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
