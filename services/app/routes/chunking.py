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


@router.post("/process")
async def process_chunk(req: ChunkRequest):
    logger.info("chunk/process request received: %s dry_run=%s overwrite=%s", req.source_id, req.dry_run, req.overwrite)
    try:
        if req.dry_run:
            # Run blocking chunker in a thread and return the result to caller
            result = await asyncio.to_thread(process_source, req.source_id, True, req.overwrite)
            return result
        else:
            # Schedule background work and return 202 Accepted immediately
            asyncio.create_task(asyncio.to_thread(process_source, req.source_id, False, req.overwrite))
            return Response(content=json.dumps({"status": "accepted", "source_id": req.source_id}), status_code=202, media_type="application/json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("unexpected error in chunk/process")
        raise HTTPException(status_code=500, detail="internal server error")

