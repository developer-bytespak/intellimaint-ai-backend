import uuid
import shutil
import os
import json
import httpx
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, Query
from fastapi.responses import JSONResponse
from app.services.batch_service import create_batch
from app.redis_client import redis_client
import asyncio
from sse_starlette.sse import EventSourceResponse
from fastapi import Query

router = APIRouter(prefix="/batches", tags=["Batches"])

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:3000/api/v1")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_batch_owner(batch_id: str):
    owner = redis_client.hget(f"batch:{batch_id}", "userId")
    # Redis returns bytes, decode if necessary
    if isinstance(owner, bytes):
        return owner.decode('utf-8')
    return owner



async def cleanup_batch(batch_id: str):
    """
    Cleanup batch when SSE disconnects during processing.
    - Clear Redis data
    - Cancel BullMQ jobs via Gateway
    """
    print(f"🧹 [CLEANUP] Starting cleanup for batch_id={batch_id}")
    
    try:
        # Get all job IDs for this batch
        job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)
        
        if not job_ids:
            print(f"🧹 [CLEANUP] No jobs found for batch_id={batch_id}")
            return
        
        # 1. Cancel jobs in BullMQ via Gateway
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{GATEWAY_URL}/internal/queue/pdf/cancel-batch",
                    json={
                        "batchId": batch_id,
                        "jobIds": job_ids
                    }
                )
                print(f"🧹 [CLEANUP] Gateway cancel response: {response.status_code}")
        except Exception as e:
            print(f"🧹 [CLEANUP] Gateway cancel failed: {e}")
        
        # 2. Clear Redis data for each job
        for job_id in job_ids:
            redis_client.delete(f"job:{job_id}")
            print(f"🧹 [CLEANUP] Deleted job:{job_id}")
        
        # 3. Clear batch data
        redis_client.delete(f"batch:{batch_id}:jobs")
        redis_client.delete(f"batch:{batch_id}")
        
        print(f"🧹 [CLEANUP] ✅ Batch {batch_id} fully cleaned up")
        
    except Exception as e:
        print(f"🧹 [CLEANUP] ❌ Error during cleanup: {e}")


@router.delete("/{batch_id}/cancel")
async def cancel_batch(batch_id: str):
    """
    Manually cancel a batch - called by frontend when user clicks cancel button
    """
    print(f"🛑 [CANCEL] Manual cancel requested for batch_id={batch_id}")
    
    # Check if batch exists
    job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)
    if not job_ids:
        raise HTTPException(404, "Batch not found")
    
    # Cleanup the batch
    await cleanup_batch(batch_id)
    
    return {"ok": True, "message": f"Batch {batch_id} cancelled and cleaned up"}


@router.post("/upload-pdfs")
async def upload_pdfs(files: List[UploadFile] = File(...),userId:str=Form(...)):
    if not files:
        raise HTTPException(400, "No files uploaded")

    file_info = []

    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Invalid file type: {f.filename}")
        
        # Save file to disk
        safe_name = f"{uuid.uuid4()}.pdf"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        # Convert to absolute path for consistency
        absolute_file_path = os.path.abspath(file_path)
        
        with open(absolute_file_path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)
        
        print(f"[batches] 💾 File saved: {absolute_file_path}")
        print(f"[batches] 📋 File exists: {os.path.exists(absolute_file_path)}")
            
        file_info.append({
            "name": f.filename,
            "path": absolute_file_path  # Use absolute path
        })

    batch_id, jobs = create_batch(file_info,userId)

    return JSONResponse({
        "batchId": batch_id,
        "status": "queued",
        "jobs": jobs
    })


@router.get("/{batch_id}")
def get_batch_status(batch_id: str,request: Request,userId:str = Query(...)):
    
    owner = get_batch_owner(batch_id)
    if not owner or owner != userId:
        raise HTTPException(403, "Forbidden: You do not own this batch")
    
    if not redis_client:
        raise HTTPException(503, "Redis unavailable")

    job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)
    if not job_ids:
        raise HTTPException(404, "Batch not found")

    jobs = []
    for job_id in job_ids:
        data = redis_client.hgetall(f"job:{job_id}")
        print(f"Fetched job data for jobId={job_id}: {data}")
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




# @router.get("/events/{batch_id}")
# async def batch_events(batch_id: str):
#     async def event_generator():
#         last_snapshot = None

#         while True:
#             job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)


#             snapshot = []
#             for job_id in job_ids:
#                  # FIX: Fetch data and inject jobId manually
#                   # FIX: Fetch data and inject jobId manually
#                 job_data = redis_client.hgetall(f"job:{job_id}")
#                 job_data["jobId"] = job_id
#                 print(f"Fetched job data for jobId={job_id}: {job_data}") 
#                 snapshot.append(job_data) # <--- CHANGED: Append the modified job_data, not the raw fetch

#             if snapshot != last_snapshot:
#                 yield {
#                     "event": "batch_update",
#                     "data": json.dumps(snapshot)
#                 }
#                 last_snapshot = snapshot

#             await asyncio.sleep(1)

#     return EventSourceResponse(event_generator())
# ...existing code...

@router.get("/events/{batch_id}")
async def batch_events(batch_id: str, request: Request, userId: str = Query(...)):
    owner = get_batch_owner(batch_id)
    if not owner or owner != userId:
        raise HTTPException(403, "Forbidden: You do not own this batch")   
    print(f"🔌 [SSE] Client connected for batch_id={batch_id}")
    
    async def event_generator():
        last_snapshot = None
        iteration = 0
        no_change_count = 0
        batch_completed = False  # Track if batch finished normally

        try:
            while True:
                # 🆕 Check if client disconnected
                if await request.is_disconnected():
                    print(f"🔌 [SSE] Client DISCONNECTED for batch_id={batch_id}")
                    break
                
                iteration += 1
                
                job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)
                
                if not job_ids:
                    no_change_count += 1
                    if no_change_count > 50:
                        print(f"⚠️ [SSE] No jobs found for 10s, closing")
                        break
                    await asyncio.sleep(0.2)
                    continue
                
                no_change_count = 0
                
                snapshot = []
                for job_id in job_ids:
                    job_data = redis_client.hgetall(f"job:{job_id}")
                    job_data["jobId"] = job_id
                    snapshot.append(job_data)

                if snapshot != last_snapshot:
                    print(f"🚀 [SSE] DATA CHANGED! Sending to frontend...")
                    event_data = json.dumps(snapshot)
                    yield {
                        "event": "batch_update",
                        "data": event_data
                    }
                    last_snapshot = snapshot

                # 🆕 Check if all jobs are done
                all_done = all(
                    job.get("status") in ["completed", "failed"] 
                    for job in snapshot
                )
                
                if all_done and len(snapshot) > 0:
                    print(f"🏁 [SSE] All jobs finished normally!")
                    batch_completed = True
                    await asyncio.sleep(0.5)
                    break

                await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            print(f"🔌 [SSE] Connection cancelled for batch_id={batch_id}")
        finally:
            # 🆕 If batch didn't complete normally, cleanup everything
            if not batch_completed:
                # Check current status before cleanup
                job_ids = redis_client.lrange(f"batch:{batch_id}:jobs", 0, -1)
                if job_ids:
                    # Check if any job is still processing
                    any_processing = False
                    for job_id in job_ids:
                        status = redis_client.hget(f"job:{job_id}", "status")
                        if status in ["queued", "processing"]:
                            any_processing = True
                            break
                    
                    if any_processing:
                        print(f"⚠️ [SSE] Client disconnected during processing! Cleaning up...")
                        await cleanup_batch(batch_id)

    return EventSourceResponse(event_generator())