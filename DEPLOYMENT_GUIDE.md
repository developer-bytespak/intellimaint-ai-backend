# IntelliMaint Deployment Guide
## Connecting Frontend to Both Backend Services

### 🏗️ Architecture Overview

```
Frontend (Your Web App)
    ├── Gateway API (Render) - Port 8000
    │   └── Handles: Auth, Users, Chat, Database, Billing
    └── AI Services (Railway) - Port 8000
        └── Handles: Vision, RAG, ASR/TTS, Streaming, Voice
```

---

## 📝 Step-by-Step Deployment

### **1️⃣ Gateway (Render) Configuration**

#### Environment Variables to Set on Render:
```env
# Database
DATABASE_URL=your_postgres_connection_string

# Frontend
FRONTEND_URL=https://your-frontend-domain.com

# JWT & Security
JWT_SECRET=your_secret_key
JWT_ACCESS_TOKEN_EXPIRY=15m
JWT_REFRESH_TOKEN_EXPIRY=7d

# AI Services Connection
AI_SERVICES_URL=https://your-railway-service.railway.app

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

### **2️⃣ AI Services (Railway) Configuration**

#### Environment Variables to Set on Railway:
```env
# Frontend CORS
ALLOWED_ORIGINS=https://your-frontend-domain.com

# Database Connection (same as Gateway)
DATABASE_URL=your_postgres_connection_string

# AI Service API Keys
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key

# Vector Database (if using Pinecone/Qdrant)
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=your_environment

# AWS S3 (for document storage)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
AWS_S3_BUCKET=your_bucket_name

# Optional: Model Configuration
VISION_MODEL=gpt-4-vision-preview
RAG_MODEL=gpt-4-turbo-preview
TTS_MODEL=tts-1
ASR_MODEL=whisper-1
```

---

### **3️⃣ Frontend Configuration**

Create or update your frontend environment file:

#### `.env` or `.env.production`:
```env
# Gateway API URL (Render)
NEXT_PUBLIC_API_URL=https://your-gateway-app.onrender.com/api/v1
# OR for React/Vite:
VITE_API_URL=https://your-gateway-app.onrender.com/api/v1
# OR for plain React:
REACT_APP_API_URL=https://your-gateway-app.onrender.com/api/v1

# AI Services URL (Railway) 
NEXT_PUBLIC_AI_SERVICES_URL=https://your-railway-service.railway.app/api/v1
# OR for React/Vite:
VITE_AI_SERVICES_URL=https://your-railway-service.railway.app/api/v1
# OR for plain React:
REACT_APP_AI_SERVICES_URL=https://your-railway-service.railway.app/api/v1

# WebSocket URLs (if using real-time features)
NEXT_PUBLIC_WS_URL=wss://your-railway-service.railway.app/api/v1/stream
```

---

## 🔧 Frontend Code Changes

### **Option A: Using Two Base URLs**

If your frontend directly calls both services:

```typescript
// config/api.ts
export const API_CONFIG = {
  gateway: {
    baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1',
    endpoints: {
      auth: '/auth',
      users: '/users',
      chat: '/chat',
      billing: '/billing',
      media: '/media',
    }
  },
  aiServices: {
    baseUrl: process.env.NEXT_PUBLIC_AI_SERVICES_URL || 'http://localhost:8000/api/v1',
    endpoints: {
      vision: '/vision',
      rag: '/rag',
      asr: '/asr',
      stream: '/stream',
      orchestrate: '/orchestrate',
    }
  }
};

// Usage in your API calls:
// For authentication
fetch(`${API_CONFIG.gateway.baseUrl}${API_CONFIG.gateway.endpoints.auth}/login`, {...})

// For AI vision analysis
fetch(`${API_CONFIG.aiServices.baseUrl}${API_CONFIG.aiServices.endpoints.vision}/analyze`, {...})
```

### **Option B: Gateway as Proxy (Recommended)**

Better approach: Let the Gateway proxy AI service requests. This way, your frontend only talks to one backend.

**Benefits:**
- Single URL for frontend
- Better security (API keys hidden)
- Easier authentication handling
- Single CORS configuration

This requires adding proxy endpoints in the Gateway (I can help with this if needed).

---

## 🚀 Deployment Steps

### **1. Deploy Gateway to Render**
```bash
cd gateway
# Make sure all changes are committed
git push origin main
```
- Go to Render dashboard
- Connect your GitHub repo
- Set build command: `npm install && npx prisma generate && npm run build`
- Set start command: `npm run start:prod`
- Add all environment variables listed above
- Deploy

### **2. Deploy AI Services to Railway**
```bash
cd services
# Make sure all changes are committed
git push origin main
```
- Go to Railway dashboard
- Create new project from GitHub repo
- Select the `services` folder
- Railway will auto-detect the Dockerfile
- Add all environment variables listed above
- Deploy

### **3. Update Frontend**
```bash
# Update your .env file with production URLs
NEXT_PUBLIC_API_URL=https://your-gateway-app.onrender.com/api/v1
NEXT_PUBLIC_AI_SERVICES_URL=https://your-railway-service.railway.app/api/v1

# Rebuild and deploy
npm run build
# Deploy to Vercel/Netlify/etc.
```

---

## 🧪 Testing the Connection

### **1. Test Gateway (Render)**
```bash
# Health check
curl https://your-gateway-app.onrender.com/api/v1/health

# Test auth endpoint
curl https://your-gateway-app.onrender.com/api/v1/auth/status
```

### **2. Test AI Services (Railway)**
```bash
# Health check
curl https://your-railway-service.railway.app/health

# Test vision endpoint
curl -X POST https://your-railway-service.railway.app/api/v1/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"image_url": "test.jpg"}'
```

### **3. Test WebSocket Connection (if using streaming)**
```javascript
const ws = new WebSocket('wss://your-railway-service.railway.app/api/v1/stream');
ws.onopen = () => console.log('Connected!');
```

---

## 🔍 Common Issues & Solutions

### **Issue 1: CORS Errors**
**Solution:** 
- Ensure `FRONTEND_URL` in Gateway includes your actual frontend domain
- Ensure `ALLOWED_ORIGINS` in AI Services includes your frontend domain
- Don't forget `https://` prefix

### **Issue 2: 502 Bad Gateway**
**Solution:**
- Check if services are running on correct ports
- Gateway default: 8000
- AI Services default: 8000
- Make sure PORT environment variable is set correctly

### **Issue 3: AI Services Not Reachable from Gateway**
**Solution:**
- Set `AI_SERVICES_URL` in Gateway to Railway public URL
- Format: `https://your-service.railway.app` (no trailing slash)

### **Issue 4: Database Connection Issues**
**Solution:**
- Both Gateway and AI Services need the same `DATABASE_URL`
- Run migrations: `npx prisma migrate deploy` in Gateway
- Make sure Postgres allows connections from both Render and Railway IPs

### **Issue 5: WebSocket Connection Fails**
**Solution:**
- Use `wss://` for production (not `ws://`)
- Check Railway allows WebSocket connections
- Verify firewall/proxy settings

---

## 📊 Architecture Flow

```
User Browser
    │
    ├─→ Auth/Users/Chat/Billing
    │       └─→ Gateway (Render)
    │               └─→ PostgreSQL Database
    │
    └─→ AI Features (Vision/RAG/Voice)
            └─→ AI Services (Railway)
                    ├─→ PostgreSQL Database (same as Gateway)
                    ├─→ OpenAI/Deepgram APIs
                    └─→ S3 for file storage
```

---

## ✅ Checklist

- [ ] Gateway deployed to Render
- [ ] AI Services deployed to Railway
- [ ] All environment variables set on Render
- [ ] All environment variables set on Railway
- [ ] Database migrations run successfully
- [ ] Frontend `.env` updated with production URLs
- [ ] CORS configured correctly on both backends
- [ ] Health endpoints tested and working
- [ ] Authentication flow tested
- [ ] AI features tested (vision, RAG, etc.)
- [ ] WebSocket streaming tested (if applicable)

---

## 🆘 Need Help?

If you encounter issues:
1. Check application logs in Render/Railway dashboards
2. Verify all environment variables are set
3. Test each service independently
4. Check network tab in browser DevTools for detailed error messages

---

**Last Updated:** December 16, 2025
