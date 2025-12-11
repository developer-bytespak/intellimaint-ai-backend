📦 intellimaint-backend/
│
├── gateway/                              # Main NestJS Backend (API Gateway)
│   ├── prisma/
│   │   ├── schema.prisma                 # All DB models (users, chats, docs, logs, billing, etc.)
│   │   ├── migrations/                   # Prisma migration files
│   │   └── seed.ts                       # Initial data seeding script
│   │
│   ├── src/
│   │   ├── modules/
│   │   │   ├── auth/                     # Email, OAuth, Passkeys (WebAuthn)
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   ├── strategies/           # OAuth + Passkey strategies
│   │   │   │   └── dto/
│   │   │   │
│   │   │   ├── users/                    # Profiles, roles, subscriptions
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   └── dto/
│   │   │   │
│   │   │   ├── chat/                     # Chat sessions, real-time updates
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   ├── gateway/              # WebSocket Gateway (NestJS)
│   │   │   │   └── dto/
│   │   │   │
│   │   │   ├── media/                    # File uploads + S3 presigned URLs
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   └── utils/
│   │   │   │
│   │   │   ├── billing/                  # Stripe billing + webhook
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   ├── webhook/              # Stripe webhook endpoints
│   │   │   │   └── dto/
│   │   │   │
│   │   │   ├── rag/                      # Document CRUD + ingestion jobs
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   └── utils/
│   │   │   │
│   │   │   ├── settings/                 # Notifications, preferences
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   └── dto/
│   │   │   │
│   │   │   ├── audit/                    # User/system activity logs
│   │   │   │   ├── services/
│   │   │   │   └── dto/
│   │   │   │
│   │   │   ├── admin/                    # Internal admin controls + RBAC
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   └── dto/
│   │   │   │
│   │   │   └── health/                   # Health check endpoints
│   │   │       └── controllers/
│   │   │
│   │   ├── realtime/                     # WebSocket / SSE layer
│   │   │   ├── chat.gateway.ts
│   │   │   └── events.ts
│   │   │
│   │   ├── common/                       # Common utilities, interceptors, guards
│   │   │   ├── decorators/
│   │   │   ├── filters/
│   │   │   ├── guards/
│   │   │   ├── interceptors/
│   │   │   └── dto/
│   │   │
│   │   ├── monitoring/                   # OpenTelemetry + Winston config
│   │   │   ├── otel.config.ts
│   │   │   └── logger.ts
│   │   │
│   │   ├── config/                       # Env config (DB, AWS, Stripe)
│   │   │   ├── app.config.ts
│   │   │   ├── aws.config.ts
│   │   │   ├── stripe.config.ts
│   │   │   └── database.config.ts
│   │   │
│   │   ├── main.ts
│   │   └── app.module.ts
│   │
│   ├── test/                             # Unit and e2e tests for Gateway
│   └── Dockerfile
│
│
├── services/                             # FastAPI Microservices (AI Layer)
│   ├── orchestrator/                     # Multimodal AI flow controller
│   │   ├── app/
│   │   │   ├── routes.py                 # /orchestrate, /status
│   │   │   ├── pipeline.py               # Flow: ASR → Vision → RAG → LLM
│   │   │   ├── safety.py                 # Role & safety guardrails
│   │   │   ├── prompts/                  # Prompt templates
│   │   │   ├── models/                   # LLM wrappers / config
│   │   │   └── utils.py
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   ├── vision_service/                   # Computer Vision + OCR
│   │   ├── detectors.py                  # YOLOv8, SAM
│   │   ├── ocr.py                        # PaddleOCR/Tesseract
│   │   ├── explain.py                    # BLIP-2 / LLaVA vision-language
│   │   ├── routes.py
│   │   ├── models/                       # Model configs
│   │   └── Dockerfile
│   │
│   ├── rag_service/                      # Retrieval-Augmented Generation
│   │   ├── embeddings.py                 # Embedding generation
│   │   ├── retriever.py                  # Semantic + keyword search
│   │   ├── reranker.py
│   │   ├── routes.py
│   │   ├── utils/
│   │   └── Dockerfile
│   │
│   ├── asr_tts_service/                  # Speech in/out (Whisper + TTS)
│   │   ├── asr.py
│   │   ├── tts.py
│   │   ├── routes.py
│   │   ├── models/
│   │   └── Dockerfile
│   │
│   └── shared/                           # Shared schemas, constants, utils
│       ├── schemas/
│       ├── constants.py
│       ├── logger.py
│       └── config.py
│
│
├── infra/                                # Infrastructure / DevOps
│   ├── docker-compose.yml                # Local development setup
│   ├── nginx.conf                        # Reverse proxy configuration
│   ├── terraform/                        # IaC for AWS
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── ecs.tf                        # ECS/Fargate microservice config
│   │   ├── rds.tf                        # Postgres setup
│   │   ├── s3.tf                         # S3 bucket config
│   │   ├── cloudfront.tf                 # CDN for media
│   │   ├── prometheus.tf
│   │   └── grafana.tf
│   │
│   ├── grafana/                          # Monitoring dashboards
│   │   ├── dashboards/
│   │   └── prometheus.yml
│   │
│   ├── github/                           # CI/CD workflows
│   │   ├── build.yml                     # Build & test
│   │   ├── deploy.yml                    # ECS deployment
│   │   └── lint.yml
│   │
│   └── README.md
│
│
├── scripts/                              # Utility scripts
│   ├── seed_db.py                        # Initialize sample data
│   ├── generate_embeddings.py             # Precompute RAG embeddings
│   ├── evaluate_models.py                 # Evaluate model performance
│   ├── backup.sh                         # Backup DB & S3
│   └── restore.sh                        # Restore backup
│
│
├── tests/                                # End-to-end integration tests
│   ├── gateway/
│   ├── services/
│   └── orchestrator/
│
└── README.md
