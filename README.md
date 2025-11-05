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
├── services/                   # Combined FastAPI AI Service
│   ├── app/                    # Main application
│   │   ├── routes/             # API routes (orchestrator, vision, rag, asr)
│   │   ├── services/           # Business logic
│   │   └── shared/             # Shared utilities
│   ├── Dockerfile              # Container configuration
│   └── requirements.txt        # Python dependencies
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
- Python 3.11, 3.12, or 3.13 (Python 3.13 is supported)
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
   cd services
   python -m venv venv
   # Windows: venv\Scripts\activate
   # macOS/Linux: source venv/bin/activate
   pip install -r requirements.txt
   python run.py
   ```

4. **Access Services**
   - Gateway API: http://localhost:3000
   - AI Service: http://localhost:8000
     - Orchestrator: `/api/v1/orchestrate`
     - Vision: `/api/v1/vision`
     - RAG: `/api/v1/rag`
     - ASR/TTS: `/api/v1/asr`

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

## Container Structure

The backend is designed for separate Docker containers:

- **Gateway Container** (`gateway/`)
  - NestJS application
  - Port: 3000
  - Self-contained with Prisma, all configs, and dependencies

- **AI Service Container** (`services/`)
  - Combined FastAPI application
  - Port: 8000
  - All AI services (orchestrator, vision, RAG, ASR/TTS) in one container

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
