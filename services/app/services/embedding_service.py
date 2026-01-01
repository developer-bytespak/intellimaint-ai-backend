# import openai
# from typing import List
# from services.batch_service import create_batches_for_embedding

# async def process_embedding_batch(data: List[str]):
#     # Process the data into chunks
#     batches = create_batches_for_embedding(data)

#     embeddings = []
#     for batch in batches:
#         # Call the API for embedding generation
#         response = openai.Embedding.create(model="text-embedding-3-small", input=batch)
#         embeddings.append(response['data'])
    
#     return embeddings


import openai
from typing import List
from services.batch_service import create_batches_for_embedding
from services.knowledge_store_service import KnowledgeStoreService
import time
from fastapi import HTTPException


async def process_embeddings_for_source(chunks: list):
    """
    Chunks ko process karke embeddings generate karta hai aur DB mein store karta hai
    chunks: List of dicts with 'id', 'chunk_index', 'content'
    """
    try:
        # Step 1: Chunks se content extract karo aur mapping banao
        chunk_mapping = []  # [{chunk_id, chunk_index, content}, ...]
        contents = []
        
        for chunk in chunks:
            chunk_mapping.append({
                "chunk_id": str(chunk['id']),
                "chunk_index": chunk['chunk_index']
            })
            contents.append(chunk['content'])
        
        print(f"Processing {len(contents)} chunks for embeddings")
        
        # Step 2: Batches banao
        batches = create_batches_for_embedding(contents)
        print(f"Created {len(batches)} batches")
        
        # Step 3: Har batch ke liye embeddings generate karo
        all_embeddings = []
        for batch_idx, batch in enumerate(batches):
            try:
                print(f"Processing batch {batch_idx + 1}/{len(batches)}")
                response = await call_openai_embedding_api(batch)
                
                # Response se embeddings extract karo
                for item in response['data']:
                    all_embeddings.append(item['embedding'])
                    
            except openai.error.RateLimitError:
                print("Rate limit reached. Retrying after delay...")
                time.sleep(5)
                response = await call_openai_embedding_api(batch)
                for item in response['data']:
                    all_embeddings.append(item['embedding'])
        
        print(f"Generated {len(all_embeddings)} embeddings")
        
        # Step 4: Chunk ID ke saath embedding pair karo
        chunk_embeddings = []
        for i, embedding in enumerate(all_embeddings):
            chunk_embeddings.append({
                "chunk_id": chunk_mapping[i]['chunk_id'],
                "embedding": embedding
            })
        
        # Step 5: DB mein update karo
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


async def process_embedding_batch(data: List[str]):
    try:
        # Process the data into chunks
        batches = create_batches_for_embedding(data)

        embeddings = []
        for batch in batches:
            # Call the API for embedding generation
            try:
                response = await call_openai_embedding_api(batch)
                embeddings.append(response['data'])
            except openai.error.RateLimitError:
                print("Rate limit reached. Retrying after delay...")
                time.sleep(5)  # Retry after 5 seconds (you can adjust this)
                response = await call_openai_embedding_api(batch)
                embeddings.append(response['data'])
            except openai.error.OpenAIError as e:
                print(f"OpenAI error occurred: {e}")
                raise HTTPException(status_code=502, detail="Error calling OpenAI API")
            except Exception as e:
                print(f"Unexpected error: {e}")
                raise HTTPException(status_code=500, detail="An unexpected error occurred during embedding process")

        return embeddings
    
    except Exception as e:
        print(f"Unexpected error in process_embedding_batch: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the embedding batch")

async def call_openai_embedding_api(batch: List[str]):
    try:
        # Call OpenAI API for embedding generation
        response = openai.Embedding.create(model="text-embedding-3-small", input=batch)
        return response
    except openai.error.RateLimitError:
        print("Rate limit exceeded. Retrying...")
        time.sleep(5)  # Exponential backoff or retry logic could be added here
        return openai.Embedding.create(model="text-embedding-3-small", input=batch)
    except openai.error.OpenAIError as e:
        print(f"Error with OpenAI API: {e}")
        raise HTTPException(status_code=502, detail="Error calling OpenAI API")
    except Exception as e:
        print(f"Unexpected error in API call: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while calling the API")

