# IntelliMaint AI Backend

Multimodal AI-powered backend for IntelliMaint maintenance and operations platform.

## Architecture

This project follows a microservices architecture with:

- **Gateway** (NestJS) - Main API gateway with authentication, user management, chat, billing, and more
- **AI Services** (FastAPI) - Microservices for orchestration, vision, RAG, and speech processing
- **Infrastructure** - Docker, Terraform (AWS ECS, RDS, S3), monitoring (Prometheus, Grafana)

See [architecture.md](./architecture.md) for detailed system design.

## Project Structure

```
📦 intellimaint-backend/
├── gateway/                    # NestJS API Gateway
│   ├── prisma/                 # Database schema & migrations
│   ├── src/                    # Source code (modules, config, monitoring)
│   └── test/                   # Unit & e2e tests
│
├── services/                   # FastAPI Microservices
│   ├── orchestrator/           # AI flow orchestration
│   ├── vision_service/         # Computer vision (YOLO, OCR, BLIP)
│   ├── rag_service/            # Document retrieval & embeddings
│   ├── asr_tts_service/        # Speech-to-text & text-to-speech
│   └── shared/                 # Shared schemas & utilities
│
├── infra/                      # Infrastructure & DevOps
│   ├── docker-compose.yml      # Local development
│   ├── terraform/              # AWS infrastructure (ECS, RDS, S3)
│   ├── grafana/                # Monitoring dashboards
│   └── github/                 # CI/CD workflows
│
├── scripts/                    # Utility scripts
│   ├── seed_db.py              # Database seeding
│   ├── generate_embeddings.py # RAG preprocessing
│   ├── backup.sh               # Backup automation
│   └── restore.sh              # Restore automation
│
└── tests/                      # Integration tests
    ├── gateway/                # Gateway API tests
    ├── services/               # Service integration tests
    └── orchestrator/           # End-to-end pipeline tests
```

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15
- AWS CLI (for deployment)

### Local Development

1. **Start infrastructure services**
   ```bash
   cd infra
   docker-compose up -d postgres redis
   ```

2. **Setup Gateway**
   ```bash
   cd gateway
   npm install
   npx prisma migrate dev
   npm run start:dev
   ```

3. **Start AI Services**
   ```bash
   # Terminal 1 - Orchestrator
   cd services/orchestrator
   pip install -r requirements.txt
   uvicorn app:app --reload --port 8000

   # Terminal 2 - Vision Service
   cd services/vision_service
   pip install -r requirements.txt
   uvicorn app:app --reload --port 8001

   # Similar for other services...
   ```

4. **Access Services**
   - Gateway API: http://localhost:3000
   - Orchestrator: http://localhost:8000
   - Vision Service: http://localhost:8001
   - RAG Service: http://localhost:8002
   - ASR/TTS Service: http://localhost:8003

### Using Docker Compose (All Services)

```bash
cd infra
docker-compose up
```

## Testing

### Gateway Tests
```bash
cd gateway
npm test                # Unit tests
npm run test:e2e        # E2E tests
```

### Service Tests
```bash
pytest tests/services/          # Service integration tests
pytest tests/orchestrator/      # Full pipeline tests
```

## Deployment

### AWS Deployment

1. **Configure AWS credentials**
   ```bash
   aws configure
   ```

2. **Deploy infrastructure**
   ```bash
   cd infra/terraform
   terraform init
   terraform apply
   ```

3. **Deploy services** (via GitHub Actions)
   - Push to `main` branch triggers automatic deployment to ECS

## Environment Variables

### Gateway (.env)
```
DATABASE_URL=postgresql://user:password@localhost:5432/intellimaint
JWT_SECRET=your-jwt-secret
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
STRIPE_SECRET_KEY=your-stripe-key
STRIPE_WEBHOOK_SECRET=your-webhook-secret
```

### Services
```
ENVIRONMENT=development
DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379
```

## Documentation

- [Architecture Overview](./architecture.md)
- [Gateway Documentation](./gateway/README.md)
- [Services Documentation](./services/README.md)
- [Infrastructure Guide](./infra/README.md)
- [Testing Guide](./tests/README.md)

## Tech Stack

### Backend (Gateway)
- NestJS, TypeScript
- Prisma ORM, PostgreSQL
- Passport (Auth), Stripe (Billing)
- Socket.io (WebSockets)
- Winston, OpenTelemetry

### AI Services
- FastAPI, Python
- OpenAI Whisper (ASR)
- YOLOv8, SAM (Vision)
- PaddleOCR/Tesseract (OCR)
- BLIP-2, LLaVA (Vision-Language)
- Sentence Transformers, FAISS (RAG)

### Infrastructure
- Docker, Docker Compose
- AWS (ECS, RDS, S3, CloudFront)
- Terraform (IaC)
- Prometheus, Grafana
- GitHub Actions (CI/CD)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

[MIT License](LICENSE)

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/intellimaint/backend/issues)
- Email: support@intellimaint.com
