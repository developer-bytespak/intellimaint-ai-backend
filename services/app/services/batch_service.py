import uuid
import httpx
import os
import json
from typing import List
from fastapi import HTTPException
from app.redis_client import redis_client

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:3000/api/v1")

def create_batch(files_info: List[dict], user_id: str):
    if not redis_client:
        raise HTTPException(503, "Redis unavailable")

    batch_id = str(uuid.uuid4())
    job_entries = []

    print(f"[batch] ======================================")
    print(f"[batch] 📦 Creating batch: {batch_id}")
    print(f"[batch] Files to process: {len(files_info)}")
    print(f"[batch] GATEWAY_URL: {GATEWAY_URL}")

    for info in files_info:
        file_name = info["name"]
        file_path = info["path"]
        job_id = str(uuid.uuid4())

        print(f"[batch] Processing file: {file_name}")
        print(f"[batch] File path: {file_path}")
        
        # Validate file exists
        if not os.path.exists(file_path):
            print(f"[batch] ⚠️ FILE NOT FOUND: {file_path}")
        else:
            file_size = os.path.getsize(file_path)
            print(f"[batch] ✅ File found (size: {file_size} bytes)")

        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "status": "queued",
                "progress": "0",
                "fileName": file_name,
                "error": ""
            }
        )

        redis_client.rpush(f"batch:{batch_id}:jobs", job_id)

        job_entries.append({
            "jobId": job_id,
            "fileName": file_name,
            "status": "queued"
        })

        print(f"[batch] 🔄 Job created: {job_id}")
        
        # Notify Gateway to add to BullMQ
        gateway_url = f"{GATEWAY_URL}/internal/queue/pdf/enqueue"
        payload = {
            "batchId": batch_id,
            "jobId": job_id,
            "fileName": file_name,
            "filePath": file_path,
            "user": {"userId": user_id, "role": "admin"}
        }
        
        print(f"[batch] 📡 Sending to gateway: {gateway_url}")
        print(f"[batch] Payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = httpx.post(gateway_url, json=payload, timeout=10.0)
            print(f"[batch] ✅ Gateway response: {response.status_code}")
            if response.status_code not in [200, 201]:
                print(f"[batch] ⚠️ Gateway error: {response.text}")
            else:
                print(f"[batch] ✅ Job enqueued successfully")
        except Exception as e:
            print(f"[batch] ❌ Failed to enqueue to gateway: {e}")
            print(f"[batch] ❌ Is gateway reachable at {GATEWAY_URL}?")

    redis_client.hset(
        f"batch:{batch_id}",
        mapping={
            "status": "queued",
            "totalJobs": len(job_entries),
            "userId": user_id
        }
    )
    
    print(f"[batch] ======================================")
    print(f"[batch] ✅ Batch created: {batch_id} with {len(job_entries)} jobs")

    return batch_id, job_entries


# def create_batches_for_embedding(chunks: List[str], max_items=2040, max_tokens=298000):

#     if not chunks:
#         return []
    
#     batches = []
#     current_batch = []
#     current_token_count = 0

#     for chunk in chunks:
#         chunk_token_count = calculate_tokens(chunk)

#         if len(current_batch) >= max_items or current_token_count + chunk_token_count > max_tokens:
#             batches.append(current_batch)
#             current_batch = []
#             current_token_count = 0

#         current_batch.append(chunk)
#         current_token_count += chunk_token_count

#     if current_batch:
#         batches.append(current_batch)

#     return batches

# def calculate_tokens(chunk: str):
#     # Assuming a simple token calculation method
#     return len(chunk.split())
def create_batches_for_embedding(chunks: List[str], max_items=2040, max_tokens=298000):
    if not chunks:
        raise ValueError("Chunks cannot be empty")
    
    batches = []
    current_batch = []
    current_token_count = 0

    for chunk in chunks:
        chunk_token_count = calculate_tokens(chunk)

        if len(current_batch) >= max_items or current_token_count + chunk_token_count > max_tokens:
            batches.append(current_batch)
            current_batch = []
            current_token_count = 0

        current_batch.append(chunk)
        current_token_count += chunk_token_count

    if current_batch:
        batches.append(current_batch)

    return batches

def calculate_tokens(chunk: str):
    if not chunk:
        raise ValueError("Chunk is empty")
    # Assuming a simple token calculation method
    return len(chunk.split())
