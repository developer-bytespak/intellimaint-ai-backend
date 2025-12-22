import uuid
import httpx
import os
from typing import List
from fastapi import HTTPException
from app.redis_client import redis_client

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:3000/api/v1")

def create_batch(files_info: List[dict],user_id:str):
    if not redis_client:
        raise HTTPException(503, "Redis unavailable")

    batch_id = str(uuid.uuid4())
    job_entries = []

    print(f"[batch] create batchId={batch_id}")

    for info in files_info:
        file_name = info["name"]
        file_path = info["path"]
        job_id = str(uuid.uuid4())

        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "status": "processing",
                "progress": "1",
                "fileName": file_name,
                "error": ""
            }
        )

        redis_client.rpush(f"batch:{batch_id}:jobs", job_id)

        job_entries.append({
            "jobId": job_id,
            "fileName": file_name,
            "status": "processing"
        })

        print(f"[batch] job queued jobId={job_id} file={file_name}")
        
        # Notify Gateway to add to BullMQ
        try:
            httpx.post(f"{GATEWAY_URL}/internal/queue/pdf/enqueue", json={
                "batchId": batch_id,
                "jobId": job_id,
                "fileName": file_name,
                "filePath": file_path,
                "user": {"userId": user_id, "role": "admin"} 
            })
        except Exception as e:
            print(f"[batch] failed to enqueue to gateway: {e}")

    redis_client.hset(
        f"batch:{batch_id}",
        mapping={
            "status": "queued",
            "totalJobs": len(job_entries)
        }
    )

    return batch_id, job_entries