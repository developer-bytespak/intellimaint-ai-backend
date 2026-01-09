"""Main FastAPI application combining all AI services"""

from pprint import pp
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


from .routes import orchestrator, vision, rag, asr_tts, doc_extract, stream, chunking, batches, doc_extract_worker , embedding_routes

import os

# Get allowed origins from environment variable
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3001,http://localhost:3000,https://intellimaint-ai.onrender.com"
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

# Add production frontends if not already in the list
production_frontends = ["https://intellimaint-ai.vercel.app", "https://intellimaint-ai.onrender.com"]
for frontend in production_frontends:
    if frontend not in allowed_origins:
        allowed_origins.append(frontend)

print(f"CORS enabled for origins: {allowed_origins}")


class SimpleCORSMiddleware(BaseHTTPMiddleware):
    """Simple CORS middleware that doesn't interfere with WebSocket connections"""
    
    async def dispatch(self, request: Request, call_next):
        # Get origin
        origin = request.headers.get("origin", "")
        
        # Handle preflight
        if request.method == "OPTIONS":
            response = Response(status_code=200)
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "600"
            return response
        
        # Process request
        response = await call_next(request)
        
        # Add CORS headers to response
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "*, Cache-Control, Content-Type"
        
        return response


# Create the FastAPI app
app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0",
)

# Use simple CORS middleware - BaseHTTPMiddleware doesn't affect WebSocket
app.add_middleware(SimpleCORSMiddleware)

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
