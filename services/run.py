import uvicorn

if __name__ == "__main__":
    print("\n🚀 Starting IntelliMaint AI Service...")
    print("📍 Server will be available at: http://localhost:8000")
    print("   Health check: http://localhost:8000/health\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

