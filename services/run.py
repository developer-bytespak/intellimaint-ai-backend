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
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

