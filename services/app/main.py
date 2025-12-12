"""Main FastAPI application combining all AI services"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import orchestrator, vision, rag, asr_tts, doc_extract, chunking

app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
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

app.include_router(
    doc_extract.router,
    prefix="/api/v1/extract",
    tags=["doc_extract"]
)
# app.include_router(
#     voice_agent.router,
#     prefix="/api/v1/upload_audio",
#     tags=["voice_agent"]
# )
# app.include_router(
app.include_router(
    chunking.router,
    prefix="/api/v1/chunk",
    tags=["chunking"]
)

#     stream.router,
#     prefix="/api/v1",
#     tags=["stream"]
# )

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

