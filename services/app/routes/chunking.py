from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.chunker import process_source

router = APIRouter()


class ChunkRequest(BaseModel):
    source_id: str
    dry_run: bool = False
    overwrite: bool = False


@router.post("/process")
async def process_chunk(req: ChunkRequest):
    try:
        result = process_source(req.source_id, dry_run=req.dry_run, overwrite=req.overwrite)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

