# IntelliMaint AI Services (FastAPI)

Microservices for AI-powered functionality.

## Services

### Orchestrator (Port 8000)
Main AI flow controller that coordinates ASR → Vision → RAG → LLM pipeline.

### Vision Service (Port 8001)
Computer vision capabilities:
- Object detection (YOLOv8, SAM)
- OCR (PaddleOCR/Tesseract)
- Image explanation (BLIP-2, LLaVA)

### RAG Service (Port 8002)
Retrieval-Augmented Generation:
- Document embeddings
- Semantic search
- Hybrid search with reranking

### ASR/TTS Service (Port 8003)
Speech processing:
- Speech-to-text (Whisper)
- Text-to-speech synthesis

## Getting Started

### Install Dependencies
Each service has its own `requirements.txt`:
```bash
cd orchestrator
pip install -r requirements.txt
```

### Run Locally
```bash
# From service directory
uvicorn app:app --reload --port 8000
```

### Run with Docker
```bash
# From infra directory
docker-compose up
```

## Shared Components

The `shared/` directory contains:
- Common schemas (Pydantic models)
- Constants and configurations
- Logging utilities
- Shared helper functions

