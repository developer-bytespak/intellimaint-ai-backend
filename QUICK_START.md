# Quick Reference: Connecting Frontend to Both Backends

## 🎯 TL;DR

### Backend Changes Required: ✅ DONE
1. ✅ Updated CORS in `services/app/main.py` to accept frontend URLs
2. ✅ Added `AI_SERVICES_URL` config to `gateway/src/config/app.config.ts`

### What You Need to Do:

## 1️⃣ Set Environment Variables on Render (Gateway)
```
FRONTEND_URL=https://your-frontend-domain.com
AI_SERVICES_URL=https://your-railway-service.railway.app
DATABASE_URL=your_postgres_url
JWT_SECRET=your_secret
GEMINI_API_KEY=your_key
# ... (see gateway/.env.example for full list)
```

## 2️⃣ Set Environment Variables on Railway (AI Services)
```
ALLOWED_ORIGINS=https://your-frontend-domain.com
DEEPGRAM_API_KEY=your_key
OPENAI_API_KEY=your_key
DATABASE_URL=your_postgres_url
# ... (see services/.env.example for full list)
```

## 3️⃣ Update Frontend Environment Variables
```env
# For Next.js:
NEXT_PUBLIC_API_URL=https://your-gateway.onrender.com/api/v1
NEXT_PUBLIC_AI_SERVICES_URL=https://your-service.railway.app/api/v1

# For Vite:
VITE_API_URL=https://your-gateway.onrender.com/api/v1
VITE_AI_SERVICES_URL=https://your-service.railway.app/api/v1

# For React:
REACT_APP_API_URL=https://your-gateway.onrender.com/api/v1
REACT_APP_AI_SERVICES_URL=https://your-service.railway.app/api/v1
```

## 4️⃣ Frontend API Usage

### For Authentication, Users, Chat Sessions, Billing:
```javascript
// Use Gateway URL
fetch('https://your-gateway.onrender.com/api/v1/auth/login', {
  method: 'POST',
  body: JSON.stringify({ email, password })
})
```

### For AI Features (Vision, RAG, Voice, Streaming):
```javascript
// Use AI Services URL
fetch('https://your-service.railway.app/api/v1/vision/analyze', {
  method: 'POST',
  body: JSON.stringify({ image_url: url })
})
```

### For WebSocket Streaming:
```javascript
const ws = new WebSocket('wss://your-service.railway.app/api/v1/stream');
```

## 📋 Service Responsibilities

### Gateway (Render) Handles:
- ✅ Authentication & Authorization
- ✅ User Management
- ✅ Chat Session Management
- ✅ Billing & Subscriptions
- ✅ Media Upload URLs
- ✅ Database Operations

### AI Services (Railway) Handles:
- ✅ Vision Analysis
- ✅ RAG (Document Q&A)
- ✅ Speech-to-Text (ASR)
- ✅ Text-to-Speech (TTS)
- ✅ WebSocket Streaming
- ✅ Voice Agent
- ✅ Document Extraction

## 🧪 Quick Test

### Test Gateway:
```bash
curl https://your-gateway.onrender.com/api/v1/health
```

### Test AI Services:
```bash
curl https://your-service.railway.app/health
```

## 📁 Files Created for Reference:
1. `DEPLOYMENT_GUIDE.md` - Complete deployment guide
2. `docs/FRONTEND_API_CONFIG_EXAMPLE.ts` - Frontend config template
3. `gateway/.env.example` - Gateway environment variables
4. `services/.env.example` - Services environment variables

## ❓ Common Questions

**Q: Do I need to make code changes in frontend?**
A: Only update environment variables to point to your deployed URLs.

**Q: Can frontend talk directly to both backends?**
A: Yes! Your frontend will call:
- Gateway for auth/users/chat sessions
- AI Services for vision/RAG/voice features

**Q: Will this cost more?**
A: You're running 2 services (Render + Railway), so yes, but it's necessary because Gateway (Node.js) and AI Services (Python) are different tech stacks.

**Q: Can I proxy everything through Gateway?**
A: Yes, you could add proxy endpoints in Gateway to forward AI requests. This would mean frontend only talks to Gateway. (Let me know if you want this approach)

---

**Next Steps:**
1. Deploy both services with environment variables
2. Update frontend .env file
3. Test endpoints
4. You're done! 🎉
