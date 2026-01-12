

# import openai
# from typing import List
# from .batch_service import create_batches_for_embedding
# from .knowledge_store_service import KnowledgeStoreService
# import time
# from fastapi import HTTPException

# client = openai.OpenAI()


# async def process_embeddings_for_source(chunks: list):
#     """
#     Chunks ko process karke embeddings generate karta hai aur DB mein store karta hai
#     chunks: List of dicts with 'id', 'chunk_index', 'content'
#     """
#     try:
#         # Step 1: Chunks se content extract karo aur mapping banao
#         chunk_mapping = []  # [{chunk_id, chunk_index, content}, ...]
#         contents = []
        
#         for chunk in chunks:
#             chunk_mapping.append({
#                 "chunk_id": str(chunk['id']),
#                 "chunk_index": chunk['chunk_index']
#             })
#             contents.append(chunk['content'])
        
#         print(f"Processing {len(contents)} chunks for embeddings")
        
#         # Step 2: Batches banao
#         batches = create_batches_for_embedding(contents)
#         print(f"Created {len(batches)} batches")
        
#         # Step 3: Har batch ke liye embeddings generate karo
#         all_embeddings = []
#         for batch_idx, batch in enumerate(batches):
#             try:
#                 print(f"Processing batch {batch_idx + 1}/{len(batches)}")
#                 response = await call_openai_embedding_api(batch)
                
                
#                 # Response se embeddings extract karo
#                 for item in response['data']:
#                     all_embeddings.append(item['embedding'])
                    
#                 print(f"Batch {batch_idx + 1} processed, total embeddings so far: {len(all_embeddings)}")
                    
#             except openai.error.RateLimitError:
#                 print("Rate limit reached. Retrying after delay...")
#                 time.sleep(5)
#                 response = await call_openai_embedding_api(batch)
#                 for item in response['data']:
#                     all_embeddings.append(item['embedding'])
        
#         print(f"Generated {len(all_embeddings)} embeddings")
        
#         # Step 4: Chunk ID ke saath embedding pair karo
#         chunk_embeddings = []
#         for i, embedding in enumerate(all_embeddings):
#             chunk_embeddings.append({
#                 "chunk_id": chunk_mapping[i]['chunk_id'],
#                 "embedding": embedding
#             })
            
#         print(f"Prepared {len(chunk_embeddings)} chunk embeddings for storage")
        
#         # Step 5: DB mein update karo
#         update_result = KnowledgeStoreService.update_chunk_embeddings(chunk_embeddings)
        
#         if not update_result:
#             raise HTTPException(status_code=500, detail="Failed to update embeddings in database")
        
#         return {
#             "embeddings_generated": len(all_embeddings),
#             "embeddings_stored": update_result['updated']
#         }
        
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         print(f"Unexpected error in process_embeddings_for_source: {e}")
#         raise HTTPException(status_code=500, detail="An error occurred while processing embeddings")



# async def call_openai_embedding_api(batch: List[str]):
#     try:
#         # Call OpenAI API for embedding generation
#         response = openai.Embedding.create(model="text-embedding-3-small", input=batch)
#         return response
#     except openai.error.RateLimitError:
#         print("Rate limit exceeded. Retrying...")
#         time.sleep(5)  # Exponential backoff or retry logic could be added here
#         return openai.Embedding.create(model="text-embedding-3-small", input=batch)
#     except openai.error.OpenAIError as e:
#         print(f"Error with OpenAI API: {e}")
#         raise HTTPException(status_code=502, detail="Error calling OpenAI API")
#     except Exception as e:
#         print(f"Unexpected error in API call: {e}")
#         raise HTTPException(status_code=500, detail="An unexpected error occurred while calling the API")
from __future__ import annotations

import asyncio
import os
from typing import List, Optional

import httpx
from fastapi import HTTPException

from .batch_service import create_batches_for_embedding
from .knowledge_store_service import KnowledgeStoreService


async def process_embeddings_for_source(chunks: list):
    try:
        chunk_mapping = []  # [{chunk_id, chunk_index, content}, ...]
        contents = []
        
        for chunk in chunks:
            chunk_mapping.append({
                "chunk_id": str(chunk['id']),
                "chunk_index": chunk['chunk_index']
            })
            contents.append(chunk['content'])

        print(f"Processing {len(contents)} chunks for embeddings")
        
        batches = create_batches_for_embedding(contents)
        print(f"Created {len(batches)} batches")
        
        all_embeddings = []
        for batch_idx, batch in enumerate(batches):
            try:
                print(f"Processing batch {batch_idx + 1}/{len(batches)}")
                response = await call_openai_embedding_api(batch)
                
                for item in response["data"]:
                    all_embeddings.append(item["embedding"])
                    
                print(f"Batch {batch_idx + 1} processed, total embeddings so far: {len(all_embeddings)}")
                    
            except HTTPException:
                raise
            except Exception as e:
                # call_openai_embedding_api already retries for 429/5xx;
                # anything reaching here is treated as a failure.
                print(f"Embedding batch failed: {e}")
                raise HTTPException(status_code=502, detail="Error calling embedding provider")
        
        print(f"Generated {len(all_embeddings)} embeddings")
        
        chunk_embeddings = []
        for i, embedding in enumerate(all_embeddings):
            chunk_embeddings.append({
                "chunk_id": chunk_mapping[i]['chunk_id'],
                "embedding": embedding
            })
        
        print(f"Prepared {len(chunk_embeddings)} chunk embeddings for storage")
        
        update_result = KnowledgeStoreService.update_chunk_embeddings(chunk_embeddings)
        
        if not update_result:
            raise HTTPException(status_code=500, detail="Failed to update embeddings in database")
        
        return {
            "embeddings_generated": len(all_embeddings),
            "embeddings_stored": update_result['updated']
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected error in process_embeddings_for_source: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing embeddings")


async def call_openai_embedding_api(batch: List[str]) -> dict:
    """
    Direct HTTP call to OpenAI embeddings endpoint (same style as scripts/embeddings/embed_family_batch.py).

    Returns a dict with at least: {"data": [{"embedding": [...]}, ...]}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key is not configured")

    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com").rstrip("/")
    url = f"{api_base}/v1/embeddings"

    body = {
        "model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        "input": batch,
        "encoding_format": "float",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Similar spirit to embed_family_batch.py: retry 429 + 5xx with exponential backoff.
    max_attempts = 4
    last_error: Optional[Exception] = None

    timeout = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.post(url, headers=headers, json=body)

                if resp.status_code < 300:
                    data = resp.json()
                    # Make sure callers can index like response["data"]
                    if not isinstance(data, dict) or "data" not in data:
                        raise HTTPException(status_code=502, detail="Unexpected embeddings response format")
                    return data

                # Retryable statuses
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    last_error = RuntimeError(f"OpenAI embeddings failed: {resp.status_code} {resp.text[:2000]}")
                else:
                    # Non-retryable error
                    raise HTTPException(status_code=502, detail=f"OpenAI embeddings error: {resp.status_code}")

            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_error = e
            except HTTPException:
                raise
            except Exception as e:
                last_error = e

            if attempt < max_attempts:
                await asyncio.sleep(2 ** attempt)

    raise HTTPException(status_code=502, detail="OpenAI embeddings failed after retries") from last_error
