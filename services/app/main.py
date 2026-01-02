"""Main FastAPI application combining all AI services"""

from pprint import pp
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware


from .routes import orchestrator, vision, rag, asr_tts, doc_extract, stream, chunking, batches, doc_extract_worker , embedding_routes

import os

# Get allowed origins from environment variable
# Format: comma-separated URLs, e.g., "https://app1.com,https://app2.com"
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3001,http://localhost:3000"
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

# Add production frontend if not already in the list
production_frontend = "https://intellimaint-ai.vercel.app"
if production_frontend not in allowed_origins:
    allowed_origins.append(production_frontend)

print(f"CORS enabled for origins: {allowed_origins}")


# Create the FastAPI app
app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0",
)

# Use allow_origins=["*"] to prevent CORSMiddleware from rejecting WebSocket connections
# Origin validation for security is done in the WebSocket endpoint itself
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins - WebSocket origin check is done in endpoint
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*", "Cache-Control", "Content-Type"],
)

# Include all routers with appropriate prefixes
app.include_router(
    orchestrator.router, prefix="/api/v1/orchestrate", tags=["orchestrator"]
)

app.include_router(vision.router, prefix="/api/v1/vision", tags=["vision"])

app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"])

app.include_router(asr_tts.router, prefix="/api/v1/asr", tags=["asr-tts"])

app.include_router(stream.router, prefix="/api/v1", tags=["stream"])

app.include_router(doc_extract.router, prefix="/api/v1/extract", tags=["doc_extract"])


app.include_router(
    chunking.router,
    prefix="/api/v1/chunk",
    tags=["chunking"]
)

app.include_router(
    batches.router,
    prefix="/api/v1",
    tags=["batches"]
)

app.include_router(
    doc_extract_worker.router,
    prefix="/api/v1/extract/internal",
    tags=["worker"]
)

app.include_router(
    embedding_routes.router,
    prefix="/api/v1",
    tags=["embedding_routes"]
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "IntelliMaint AI Service",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}
