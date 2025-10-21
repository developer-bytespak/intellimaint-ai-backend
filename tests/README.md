# Integration Tests

End-to-end integration tests for IntelliMaint backend services.

## Structure

- `gateway/` - NestJS Gateway API tests
- `services/` - FastAPI microservice tests
- `orchestrator/` - Full pipeline integration tests

## Running Tests

### Gateway Tests
```bash
cd gateway
npm test
```

### Service Tests
```bash
pytest tests/services/
```

### Full Integration Tests
```bash
pytest tests/orchestrator/
```

## Requirements

- Docker Compose (for running services)
- Node.js 20+ (for Gateway tests)
- Python 3.11+ (for service tests)

