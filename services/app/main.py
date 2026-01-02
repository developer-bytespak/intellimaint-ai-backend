"""Main FastAPI application combining all AI services"""

from pprint import pp
from fastapi import FastAPI, Request
from starlette.types import ASGIApp, Receive, Scope, Send


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


class CORSMiddlewareWithWebSocket:
    """Custom CORS middleware that properly handles WebSocket connections.
    
    The standard FastAPI CORSMiddleware returns 403 for WebSocket connections
    from origins not in the allowed list. This middleware allows WebSocket
    connections to pass through (origin validation is done in the WS endpoint).
    """
    
    def __init__(self, app: ASGIApp, allowed_origins: list[str]):
        self.app = app
        self.allowed_origins = set(allowed_origins)
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "websocket":
            # For WebSocket, just pass through - origin check happens in the endpoint
            await self.app(scope, receive, send)
            return
        
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Handle HTTP requests with CORS
        headers_list = scope.get("headers", [])
        headers = {k: v for k, v in headers_list}
        origin = headers.get(b"origin", b"").decode()
        method = scope.get("method", "GET")
        
        # Check if origin is allowed
        origin_allowed = origin in self.allowed_origins or "*" in self.allowed_origins or not origin
        
        # Handle preflight OPTIONS request
        if method == "OPTIONS":
            response_headers = [
                (b"access-control-allow-methods", b"GET, POST, PUT, DELETE, PATCH, OPTIONS"),
                (b"access-control-allow-headers", b"*"),
                (b"access-control-max-age", b"600"),
            ]
            if origin_allowed and origin:
                response_headers.append((b"access-control-allow-origin", origin.encode()))
                response_headers.append((b"access-control-allow-credentials", b"true"))
            
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": response_headers,
            })
            await send({
                "type": "http.response.body",
                "body": b"",
            })
            return
        
        # For other requests, add CORS headers to response
        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                resp_headers = list(message.get("headers", []))
                if origin_allowed and origin:
                    resp_headers.append((b"access-control-allow-origin", origin.encode()))
                    resp_headers.append((b"access-control-allow-credentials", b"true"))
                    resp_headers.append((b"access-control-expose-headers", b"*, Cache-Control, Content-Type"))
                message = {**message, "headers": resp_headers}
            await send(message)
        
        await self.app(scope, receive, send_with_cors)


# Create the FastAPI app
fastapi_app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0",
)

# Include all routers with appropriate prefixes
fastapi_app.include_router(
    orchestrator.router, prefix="/api/v1/orchestrate", tags=["orchestrator"]
)

fastapi_app.include_router(vision.router, prefix="/api/v1/vision", tags=["vision"])

fastapi_app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"])

fastapi_app.include_router(asr_tts.router, prefix="/api/v1/asr", tags=["asr-tts"])

fastapi_app.include_router(stream.router, prefix="/api/v1", tags=["stream"])

fastapi_app.include_router(doc_extract.router, prefix="/api/v1/extract", tags=["doc_extract"])


fastapi_app.include_router(
    chunking.router,
    prefix="/api/v1/chunk",
    tags=["chunking"]
)

fastapi_app.include_router(
    batches.router,
    prefix="/api/v1",
    tags=["batches"]
)

fastapi_app.include_router(
    doc_extract_worker.router,
    prefix="/api/v1/extract/internal",
    tags=["worker"]
)

fastapi_app.include_router(
    embedding_routes.router,
    prefix="/api/v1",
    tags=["embedding_routes"]
)


@fastapi_app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "IntelliMaint AI Service",
        "version": "1.0.0",
    }


@fastapi_app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


# Wrap with custom CORS middleware that handles WebSocket properly
# This is the app that uvicorn will use
app = CORSMiddlewareWithWebSocket(fastapi_app, allowed_origins)
