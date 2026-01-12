# Document Processing Pipeline - Production Fix Guide

## Problem
When uploading PDF documents in production, the pipeline fails after 1-2 seconds with the error:
```
"Processing failed. Page will reload."
```

This happens locally but works fine in development.

## Root Causes

### 1. **Hardcoded localhost URLs**
The PDF worker in the Gateway was calling:
```typescript
const pythonUrl = `http://localhost:8000/api/v1/extract/internal/run`;
```

In production, `http://localhost:8000` doesn't exist! The services are on a different server/container.

### 2. **Missing Environment Variables**
The following environment variables were not being set in production:
- `PYTHON_BASE_URL` on Render Gateway
- `GATEWAY_URL` on Railway Services

Without these, the services communicate incorrectly.

### 3. **Architecture Mismatch**
```
❌ BEFORE (Wrong):
Frontend → Gateway (Render) → Worker tries to call localhost:8000 → FAILS

✅ AFTER (Correct):
Frontend → Gateway (Render, uses PYTHON_BASE_URL) → Services (Railway) → Extraction, Chunking, Embedding
Services → Gateway (uses GATEWAY_URL) → Queue (BullMQ) → Job processing
```

## Changes Made

### 1. Fixed Worker URL Usage
**File**: `gateway/src/modules/queue/pdf.worker.ts`

```diff
- const pythonUrl = `http://localhost:8000/api/v1/extract/internal/run`;
+ const pythonUrl = `${PYTHON_BASE}/api/v1/extract/internal/run`;
```

Where `PYTHON_BASE` comes from:
```typescript
const PYTHON_BASE = process.env.PYTHON_BASE_URL || "http://localhost:8000";
```

### 2. Added Environment Variables to Docker Compose
**File**: `docker-compose.yml`

**Gateway Environment**:
```yaml
PYTHON_BASE_URL: ${PYTHON_BASE_URL:-http://services:8000}
```

**Services Environment**:
```yaml
GATEWAY_URL: ${GATEWAY_URL:-http://gateway:3000/api/v1}
```

### 3. Updated Production Environment Documentation
**File**: `PRODUCTION_ENV_SETUP.md`

Added critical section explaining which variables go where.

## How to Deploy

### Step 1: Render (Gateway) Environment Variables
Set these in your Render dashboard:
```
PYTHON_BASE_URL=https://your-railway-service.railway.app
```

### Step 2: Railway (Services) Environment Variables
Set these in your Railway dashboard:
```
GATEWAY_URL=https://your-render-gateway.onrender.com/api/v1
```

### Step 3: Deploy Updated Code
```bash
# If using Docker:
docker-compose up -d --build

# If using git push deployment:
git add .
git commit -m "Fix production document processing pipeline"
git push
```

### Step 4: Verify Deployment
Check the logs:
```bash
# Gateway logs should show:
[worker] PYTHON_BASE_URL = https://your-railway-service.railway.app

# Services logs should show:
[batch] 📡 Sending to gateway: https://your-render-gateway.onrender.com/api/v1/internal/queue/pdf/enqueue
```

## Document Processing Flow (Now Fixed)

1. **Frontend** uploads PDF to `/api/upload-repository-document`
2. **Frontend** calls `/api/v1/batches/upload-pdfs` with file
3. **Gateway** routes to **Services** `/api/v1/batches/upload-pdfs`
4. **Services** creates batch and enqueues jobs via **Gateway** `/api/v1/internal/queue/pdf/enqueue`
5. **Gateway** worker picks up job and calls **Services** `/api/v1/extract/internal/run` (NOW USES PYTHON_BASE_URL ✅)
6. **Services** extracts text, updates Redis
7. **Frontend** connects SSE to **Services** `/api/v1/batches/events/{batchId}` for real-time updates
8. **Services** calls **Gateway** to cancel jobs if SSE disconnects (NOW USES GATEWAY_URL ✅)

## Local Development

For local development with Docker Compose:
- No changes needed - uses service names (gateway, services)
- Make sure containers are on same network: `intellimaint-network`

For local development without Docker:
- Services on `http://localhost:8000`
- Gateway on `http://localhost:3000`
- No environment variables needed - uses defaults

## Testing the Fix

### Test 1: Upload a Document
1. Go to Repository page
2. Upload a PDF
3. Click "Send to Repository"
4. Check console for "processing failed" error
5. ✅ Should NOT see error now

### Test 2: Check Logs
```bash
# Watch Gateway worker logs
docker logs intellimaint-gateway | grep "PYTHON_BASE_URL\|Calling Python\|⚠️\|❌"

# Watch Services batch logs
docker logs intellimaint-services | grep "📡 Sending to gateway\|enqueue\|failed"
```

### Test 3: Monitor Redis
```bash
# Check job status
redis-cli HGETALL job:YOUR_JOB_ID
redis-cli LRANGE batch:YOUR_BATCH_ID:jobs 0 -1
```

## Troubleshooting

### Still Failing After 1-2 Seconds?

**Check 1**: Verify environment variables are set
```bash
# Render (Gateway)
echo $PYTHON_BASE_URL

# Railway (Services)
echo $GATEWAY_URL
```

**Check 2**: Verify URLs are correct
```bash
# Gateway should be able to reach:
curl https://your-railway-service.railway.app/api/v1/health

# Services should be able to reach:
curl https://your-render-gateway.onrender.com/api/v1/health
```

**Check 3**: Check logs for the actual error
```bash
# Look for error messages in worker:
"[worker] ❌ ERROR jobId=..."
"[worker] Full error: ..."

# Look for connection errors:
"ECONNREFUSED\|ETIMEDOUT\|ENOTFOUND"
```

### Connection Timeout Errors?
- Increase timeout in pdf.worker.ts if extraction takes >30 minutes
- Check if services is actually running
- Check if there's a firewall blocking the connection

### "Cannot POST /api/v1/extract/internal/run" Error?
- Make sure you're using the full URL: `/api/v1/extract/internal/run`
- Not just `/extract/internal/run`

## Summary of Fixed Issues

| Issue | Location | Before | After |
|-------|----------|--------|-------|
| Hardcoded URL | pdf.worker.ts:58 | `http://localhost:8000/api/v1/extract/internal/run` | `${PYTHON_BASE}/api/v1/extract/internal/run` |
| Missing env var | docker-compose.yml | Not set | `PYTHON_BASE_URL` |
| Missing env var | docker-compose.yml | Not set | `GATEWAY_URL` |
| Documentation | PRODUCTION_ENV_SETUP.md | Incomplete | Complete with all required vars |

## References
- [Docker Compose Config](./docker-compose.yml)
- [PDF Worker Code](./gateway/src/modules/queue/pdf.worker.ts)
- [Batch Service](./services/app/services/batch_service.py)
- [Production Setup Guide](./PRODUCTION_ENV_SETUP.md)
