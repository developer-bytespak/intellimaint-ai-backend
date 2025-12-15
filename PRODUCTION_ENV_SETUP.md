# Production Environment Variables Setup

## ⚙️ Railway (Services Backend)

Set these environment variables in your Railway dashboard:

```env
# CORS Configuration
ALLOWED_ORIGINS=https://intellimaint-ai.vercel.app,http://localhost:3000,http://localhost:3001

# Database (if needed)
DATABASE_URL=your_postgres_connection_string

# AI Service API Keys
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key

# AWS S3 (for document storage)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
AWS_S3_BUCKET=your_bucket_name

# Optional: Port (Railway usually auto-sets this)
PORT=8000
```

---

## ⚙️ Render (Gateway Backend)

Set these environment variables in your Render dashboard:

```env
# CORS Configuration
FRONTEND_URL=https://intellimaint-ai.vercel.app,http://localhost:3000,http://localhost:3001

# Database
DATABASE_URL=your_postgres_connection_string

# JWT & Security
JWT_SECRET=your_secret_key
JWT_ACCESS_TOKEN_EXPIRY=15m
JWT_REFRESH_TOKEN_EXPIRY=7d

# AI Services Connection (Railway URL)
AI_SERVICES_URL=https://intellimaint-ai-backend-production.up.railway.app

# Redis (if using)
REDIS_URL=your_redis_url
REDIS_PORT=6379

# AWS S3 (for media uploads)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
AWS_S3_BUCKET=your_bucket_name

# Stripe (for billing)
STRIPE_SECRET_KEY=your_stripe_key
STRIPE_WEBHOOK_SECRET=your_webhook_secret

# Google OAuth (if using)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_CALLBACK_URL=https://your-render-app.onrender.com/api/v1/auth/google/callback

# Email Service
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Gemini AI
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL_NAME=gemini-2.5-flash
```

---

## ⚙️ Vercel (Frontend)

Set these environment variables in your Vercel project settings:

```env
# Gateway on Render
NEXT_PUBLIC_NEST_URL=https://your-gateway.onrender.com

# Services on Railway
NEXT_PUBLIC_API_URL=https://intellimaint-ai-backend-production.up.railway.app

# WebSocket on Railway
NEXT_PUBLIC_WEBSOCKET_URL=wss://intellimaint-ai-backend-production.up.railway.app/api/v1/stream

# Blob storage (if using)
BLOB_READ_WRITE_TOKEN=your_vercel_blob_token
```

---

## 🚀 Deployment Steps After Code Changes

### 1. Deploy Services to Railway
```bash
cd services
git add .
git commit -m "Fix CORS for production"
git push
```

### 2. Deploy Gateway to Render
```bash
cd gateway
git add .
git commit -m "Fix CORS for production"
git push
```

### 3. Verify Environment Variables
- **Railway**: Check that `ALLOWED_ORIGINS` is set correctly
- **Render**: Check that `FRONTEND_URL` is set correctly
- **Vercel**: Check that all `NEXT_PUBLIC_*` variables are set

### 4. Test the Connection
Open your browser console on `https://intellimaint-ai.vercel.app` and check:
- No CORS errors
- Requests to Railway backend succeed
- WebSocket connection establishes successfully

---

## ✅ Quick Checklist

- [ ] Updated `services/app/main.py` with CORS fix
- [ ] Updated `gateway/src/main.ts` with CORS fix
- [ ] Set `ALLOWED_ORIGINS` on Railway
- [ ] Set `FRONTEND_URL` on Render
- [ ] Pushed code changes to repository
- [ ] Railway auto-deployed successfully
- [ ] Render auto-deployed successfully
- [ ] Tested frontend - no CORS errors
- [ ] WebSocket streaming works

---

## 🔍 Troubleshooting

**Still getting CORS errors?**
1. Check Railway logs: Verify the CORS origins are printed on startup
2. Check Render logs: Verify the CORS origins are printed on startup
3. Clear browser cache and hard refresh (Ctrl+Shift+R)
4. Check that environment variables are set correctly (no typos)
5. Verify the frontend URL matches exactly (with https://)

**WebSocket not connecting?**
1. Use `wss://` (not `ws://`) for production
2. Check Railway allows WebSocket connections
3. Verify the endpoint path is `/api/v1/stream`

---

**Last Updated:** December 16, 2025
