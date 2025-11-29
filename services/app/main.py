"""Main FastAPI application combining all AI services"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import orchestrator, vision, rag, asr_tts , doc_extract
from .shared.database import get_db, check_db_connection
app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins - change to specific origins in production
    allow_credentials=False,  # Cannot be True when allow_origins=["*"]
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
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

@app.get("/")
async def test_db():
    return check_db_connection()

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}