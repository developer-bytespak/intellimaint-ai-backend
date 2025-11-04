from fastapi import APIRouter, HTTPException
from ..services.orchestrator_service import orchestrate_request

router = APIRouter()

@router.post("/orchestrate")
async def orchestrate(request: dict):
    """Main orchestration endpoint for multimodal AI flow"""
    try:
        result = await orchestrate_request(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get orchestration job status"""
    return {"jobId": job_id, "status": "processing"}

