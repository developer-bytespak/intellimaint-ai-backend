from fastapi import APIRouter, HTTPException, status, Response
from pydantic import BaseModel
import asyncio
import logging
import json

from ..services.chunker import process_source

router = APIRouter()
logger = logging.getLogger(__name__)


class ChunkRequest(BaseModel):
    source_id: str
    dry_run: bool = False
    overwrite: bool = False


class ChunkResponse(BaseModel):
    source_id: str
    num_chunks: int
    status: str = "success"


@router.post("/process", response_model=ChunkResponse)
async def process_chunk(req: ChunkRequest):
    """
    Process a knowledge source and create chunks.
    
    - Uses the universal PDF chunker with 15% overlap
    - English-only filtering applied
    - Automatically retries once on failure
    
    Args:
        source_id: UUID of the knowledge source
        dry_run: If True, returns chunks without inserting to DB
        overwrite: If True, deletes existing chunks before inserting
    
    Returns:
        ChunkResponse with source_id, num_chunks, and status
    """
    logger.info("chunk/process request received: %s dry_run=%s overwrite=%s", req.source_id, req.dry_run, req.overwrite)
    try:
        print("Starting chunk processing for source_id:", req.source_id)
        # Run blocking chunker in a thread (sync processing)
        result = await asyncio.to_thread(process_source, req.source_id, req.dry_run, req.overwrite)
        
        return ChunkResponse(
            source_id=result.get("source_id", req.source_id),
            num_chunks=result.get("num_chunks", 0),
            status="success"
        )
    except ValueError as e:
        logger.warning("chunk/process validation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("unexpected error in chunk/process")
        raise HTTPException(status_code=500, detail=f"Chunking failed: {str(e)}")

