# IntelliMaint AI Service

Combined FastAPI service for all AI functionality including vision, RAG, ASR/TTS, and orchestration.

## Structure

```
services/
├── app/
│   ├── main.py              # Main FastAPI application
│   ├── routes/              # API route handlers
│   │   ├── orchestrator.py
│   │   ├── vision.py
│   │   ├── rag.py
│   │   └── asr_tts.py
│   ├── services/            # Business logic
│   │   ├── orchestrator_service.py
│   │   ├── vision_service.py
│   │   ├── rag_service.py
│   │   ├── asr_tts_service.py
│   │   └── safety.py
│   └── shared/              # Shared utilities
│       ├── config.py
│       ├── constants.py
│       ├── logger.py
│       └── schemas/
├── Dockerfile
├── requirements.txt
├── run.py
└── README.md
```

## API Endpoints

All endpoints run on port 8000:

### Orchestrator
- `POST /api/v1/orchestrate` - Main orchestration endpoint
- `GET /api/v1/orchestrate/status/{job_id}` - Get job status

### Vision Service
- `POST /api/v1/vision/detect` - Detect objects in image
- `POST /api/v1/vision/ocr` - Extract text from image
- `POST /api/v1/vision/explain` - Generate image explanation

### RAG Service
- `POST /api/v1/rag/search` - Search for relevant documents
- `POST /api/v1/rag/embed` - Generate embeddings for texts

### ASR/TTS Service
- `POST /api/v1/asr/transcribe` - Transcribe audio file
- `POST /api/v1/asr/synthesize` - Convert text to speech

### Health Check
- `GET /` - Root endpoint
- `GET /health` - Health check

## Getting Started

### Install Dependencies

**Important:** This project requires Python 3.11, 3.12, or 3.13.

```bash
cd services

# Create and activate virtual environment (recommended)
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run Locally

**Option 1: Using run.py (simplest)**
```bash
python run.py
```

**Option 2: Using uvicorn directly**
```bash
uvicorn app.main:app --reload --port 8000
```

### Run with Docker

```bash
# Build image
docker build -t ai-service ./services

# Run container
docker run -p 8000:8000 ai-service
```

## Environment Variables

```env
ENVIRONMENT=development
LOG_LEVEL=INFO
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
```

## Dependencies

- FastAPI - Web framework
- Uvicorn - ASGI server
- httpx - HTTP client for API calls
- Pydantic - Data validation
- python-multipart - File uploads
- Pillow - Image handling

