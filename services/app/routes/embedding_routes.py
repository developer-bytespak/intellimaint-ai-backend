# from fastapi import APIRouter
# from services.embedding_service import process_embedding_batch

# router = APIRouter()

# @router.post("/generate-embeddings")
# async def generate_embeddings(data: list):
#     # Calls the embedding service to process a batch of chunks
#     return await process_embedding_batch(data)


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.embedding_service import process_embeddings_for_source
from services.knowledge_store_service import KnowledgeStoreService

router = APIRouter()


class EmbeddingRequest(BaseModel):
    source_id: str


@router.post("/generate-embeddings")
async def generate_embeddings(request: EmbeddingRequest):
    """
    source_id se chunks fetch karke embeddings generate aur store karta hai
    """
    try:
        source_id = request.source_id
        
        if not source_id:
            raise HTTPException(status_code=400, detail="source_id is required")
        
        # Step 1: Chunks fetch karo source_id se
        chunks = KnowledgeStoreService.get_chunks_by_source_id(source_id)
        
        if not chunks:
            raise HTTPException(status_code=404, detail="No chunks found for this source_id")
        
        print(f"Processing {len(chunks)} chunks for source_id: {source_id}")
        
        # Step 2: Embeddings generate aur store karo
        result = await process_embeddings_for_source(chunks)
        
        return {
            "status": "success",
            "source_id": source_id,
            "chunks_processed": len(chunks),
            "result": result
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while processing embeddings")
