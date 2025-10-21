# IntelliMaint Gateway (NestJS)

Main API Gateway for IntelliMaint backend.

## Structure

- `prisma/` - Database schema and migrations
- `src/modules/` - Feature modules (auth, users, chat, media, billing, etc.)
- `src/config/` - Configuration files
- `src/monitoring/` - OpenTelemetry and Winston logging
- `src/realtime/` - WebSocket/SSE implementation
- `src/common/` - Shared utilities, guards, interceptors
- `test/` - Unit and e2e tests

## Getting Started

### Install Dependencies
```bash
npm install
```

### Setup Database
```bash
npx prisma migrate dev
npx prisma generate
npm run seed
```

### Development
```bash
npm run start:dev
```

### Build
```bash
npm run build
```

### Test
```bash
npm test
npm run test:e2e
```

## Environment Variables

Create a `.env` file with:
```
DATABASE_URL=postgresql://user:password@localhost:5432/intellimaint
JWT_SECRET=your-secret-key
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
STRIPE_SECRET_KEY=your-stripe-key
```

