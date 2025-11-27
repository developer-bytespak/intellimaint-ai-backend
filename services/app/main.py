from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from .shared.database import init_connection_pool, close_all_connections, test_connection

# Use async context manager for lifespan to handle startup and shutdown properly
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown.
    Handles the database connection pool and ensures it's cleaned up.
    """
    print("🚀 Application is starting...")

    # STARTUP: Test DB connection and initialize pool
    try:
        print("🔍 Testing database connection...")
        if test_connection():
            print("✅ Database connection test successful")
            # Initialize the connection pool
            print("🔧 Initializing connection pool...")
            init_connection_pool(min_conn=2, max_conn=10)
            print("✅ Connection pool initialized")
        else:
            print("⚠️ Database connection test failed")
            print("⚠️ Application will continue without database")
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        print("⚠️ Application will continue without DB")

    yield  # The application is now running

    # SHUTDOWN: Cleanup resources (close DB connections)
    print("\n🛑 Application is shutting down...")
    try:
        close_all_connections()  # Gracefully close all database connections
        print("✅ All database connections closed")
    except Exception as e:
        print(f"⚠️ Error closing DB connections: {e}")

    print("✅ Application shutdown complete")

# FastAPI app with lifespan manager
app = FastAPI(
    title="IntelliMaint AI Service",
    description="Combined AI service for vision, RAG, ASR/TTS, and orchestration",
    version="1.0.0",
    lifespan=lifespan  # Attach the lifespan manager here
)

