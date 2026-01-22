"""Main FastAPI application combining all AI services"""

from pprint import pp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import gc
import asyncio

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


class MemoryLimiterMiddleware(BaseHTTPMiddleware):
    """FIX P1: Monitors memory and rejects requests if memory is critical"""
    
    def __init__(self, app):
        super().__init__(app)
        try:
            import psutil
            self.process = psutil.Process()
            self.psutil_available = True
        except ImportError:
            print("⚠️  psutil not installed, memory limiting disabled")
            self.psutil_available = False
        self.request_count = 0
    
    async def dispatch(self, request: Request, call_next):
        if not self.psutil_available:
            return await call_next(request)
        
        path = request.url.path
        self.request_count += 1
        
        # Skip health checks
        if path in ["/health", "/", "/api/v1/health"]:
            return await call_next(request)
        
        # Check current memory
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        
        # Log every 50 requests
        if self.request_count % 50 == 0:
            print(f"📊 [MEMORY] Current: {memory_mb:.0f}MB / 512MB | Requests: {self.request_count}")
        
        # If very high, try garbage collection first
        if memory_mb > 400:
            print(f"⚠️ High memory ({memory_mb:.0f}MB), running GC...")
            gc.collect()
            memory_mb = self.process.memory_info().rss / 1024 / 1024
        
        # If still critical, reject request
        if memory_mb > 450:
            print(f"🚨 CRITICAL memory ({memory_mb:.0f}MB), rejecting request")
            return JSONResponse(
                {
                    "error": "Server is out of memory",
                    "memory_mb": round(memory_mb, 1),
                    "message": "Please try again in a moment"
                },
                status_code=503
            )
        
        # Process request normally
        try:
            response = await call_next(request)
            return response
        finally:
            # After request, check if we should warn
            final_memory = self.process.memory_info().rss / 1024 / 1024
            if final_memory > 400:
                print(f"⚠️ Memory still high after request: {final_memory:.0f}MB")


# Create the FastAPI app
app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0",
)

# Use memory limiter FIRST, then CORS
app.add_middleware(SimpleCORSMiddleware)
app.add_middleware(MemoryLimiterMiddleware)

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


@app.on_event("startup")
async def startup_event():
    """Log memory status periodically"""
    async def log_memory():
        while True:
            try:
                import psutil
                mem_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
                if mem_mb > 450:
                    print(f"🔴 [MEMORY] CRITICAL: {mem_mb:.0f}MB")
                elif mem_mb > 400:
                    print(f"🟠 [MEMORY] HIGH: {mem_mb:.0f}MB")
                else:
                    print(f"🟢 [MEMORY] OK: {mem_mb:.0f}MB")
                await asyncio.sleep(60)
            except Exception as e:
                print(f"Memory logging error: {e}")
                await asyncio.sleep(60)
    
    asyncio.create_task(log_memory())
