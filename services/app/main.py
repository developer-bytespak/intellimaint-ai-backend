"""Main FastAPI application combining all AI services"""

from fastapi import FastAPI
from .routes import orchestrator, vision, rag, asr_tts

app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0"
)

# Include all routers with appropriate prefixes
app.include_router(
    orchestrator.router,
    prefix="/api/v1/orchestrate",
    tags=["orchestrator"]
)

app.include_router(
    vision.router,
    prefix="/api/v1/vision",
    tags=["vision"]
)

app.include_router(
    rag.router,
    prefix="/api/v1/rag",
    tags=["rag"]
)

app.include_router(
    asr_tts.router,
    prefix="/api/v1/asr",
    tags=["asr-tts"]
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "IntelliMaint AI Service",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

