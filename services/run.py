import uvicorn
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

if __name__ == "__main__":
    print("\n🚀 Starting IntelliMaint AI Service...")
    print("📍 Server will be available at: http://localhost:8000")
    print("   Health check: http://localhost:8000/health\n")
    
    # Verify API keys are loaded
    if os.getenv("DEEPGRAM_API_KEY"):
        print("✅ DEEPGRAM_API_KEY loaded successfully")
    else:
        print("⚠️  WARNING: DEEPGRAM_API_KEY not found in environment")
    
    print("⚠️  MEMORY OPTIMIZATION: Running in single-worker mode")
    print("⚠️  Concurrency limited to 3 requests (allows upload + chat + buffer)\n")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,
        limit_concurrency=3,
        timeout_keep_alive=5
    )

