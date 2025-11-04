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

Create a `.env` file in the `gateway/` directory with the following variables:

### Required Variables
```env
# Application
PORT=3000
NODE_ENV=development
API_PREFIX=/api/v1

# Database (required for Prisma)
DATABASE_URL=postgresql://user:password@localhost:5432/intellimaint?schema=public

# JWT Authentication (required)
JWT_SECRET=your-super-secret-jwt-key-change-this-in-production
```

### Optional Variables
```env
# AWS Configuration (for S3, etc.)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_S3_BUCKET=

# Stripe Configuration (for billing)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

**Note:** The `JWT_SECRET` environment variable is **required** for the application to start. Without it, you'll get an error: `JwtStrategy requires a secret or key`.

