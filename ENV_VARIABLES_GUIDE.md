# Environment Variables Guide

## Backend Services Architecture

The IntelliMaint backend consists of **two separate services**:

1. **NestJS Gateway** (Render) - Port 8000
   - All `/api/v1/*` HTTP REST endpoints
   - Socket.IO websocket server for real-time chat (`/chat` namespace)
   - Authentication, sessions, user management
   - **Chat system with Gemini AI** (self-contained, no Python needed)
   - Database operations (PostgreSQL via Prisma)

2. **Python Services** (Railway/Render) - Port 8000
   - AI processing endpoints (RAG, embeddings, etc.)
   - Document processing
   - Advanced analytics
   - **NOT used by the current chat implementation**

## Frontend Environment Variables

### Required for Chat & Auth

```env
# NestJS Gateway URL (REQUIRED for chat, auth, all /api/v1 endpoints)
NEXT_PUBLIC_NEST_URL=https://intellimaint-ai-backend.onrender.com

# DO NOT include /api/v1 in the URL above - it's added in code
```

### Optional - Python Services

```env
# Python Services URL (OPTIONAL - only if using Python-specific features)
NEXT_PUBLIC_API_URL=https://intellimaint-ai-backend-production.up.railway.app
```

## Frontend Code Examples

### Socket.IO Connection (Chat)

```ts
import { io } from 'socket.io-client';

// Use NEST_URL for Socket.IO
const NEST_URL = process.env.NEXT_PUBLIC_NEST_URL!;

export const socket = io(`${NEST_URL}/chat`, {
  path: '/socket.io',
  transports: ['websocket'],
  withCredentials: true,
});
```

### HTTP API Calls (Auth, Sessions, etc.)

```ts
// Use NEST_URL + /api/v1 for REST endpoints
const NEST_URL = process.env.NEXT_PUBLIC_NEST_URL!;
const API_BASE = `${NEST_URL}/api/v1`;

// Login
await fetch(`${API_BASE}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ email, password }),
});

// Get chat sessions
const sessions = await fetch(`${API_BASE}/chat/sessions`, {
  credentials: 'include',
});
```

### If You Need Python Services

```ts
// Only if using Python-specific features (RAG, etc.)
const PYTHON_URL = process.env.NEXT_PUBLIC_API_URL!;

const embeddings = await fetch(`${PYTHON_URL}/embeddings`, {
  method: 'POST',
  // ...
});
```

## Backend Environment Variables

### Gateway (.env on Render)

```env
# Core
NODE_ENV=production
PORT=8000
DATABASE_URL=postgresql://...

# Frontend CORS
FRONTEND_URL=https://your-app.vercel.app

# Gemini AI (used by chat)
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL_NAME=gemini-2.5-flash

# Python Services URL (if gateway needs to call Python)
AI_SERVICES_URL=https://your-python-service.railway.app

# Auth
JWT_SECRET=your-secret
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Storage
BLOB_READ_WRITE_TOKEN=vercel_blob_...
```

### Python Services (.env on Railway)

```env
PORT=8000
# Database, API keys for Python-specific features
# ...
```

## Common Mistakes to Avoid

❌ **Wrong:** Using `NEXT_PUBLIC_API_URL` for Socket.IO
```ts
// This connects to Python service, not Gateway!
const socket = io(`${process.env.NEXT_PUBLIC_API_URL}/chat`);
```

✅ **Correct:** Use `NEXT_PUBLIC_NEST_URL` for Socket.IO
```ts
const socket = io(`${process.env.NEXT_PUBLIC_NEST_URL}/chat`);
```

---

❌ **Wrong:** Including `/api/v1` in env var
```env
NEXT_PUBLIC_NEST_URL=https://gateway.onrender.com/api/v1
```

✅ **Correct:** Add `/api/v1` in code, not env
```env
NEXT_PUBLIC_NEST_URL=https://gateway.onrender.com
```
```ts
const API_BASE = `${process.env.NEXT_PUBLIC_NEST_URL}/api/v1`;
```

---

❌ **Wrong:** Using `/api/v1/socket.io` path
```ts
const socket = io(url, { path: '/api/v1/socket.io' });
```

✅ **Correct:** Socket.IO always uses root path
```ts
const socket = io(url, { path: '/socket.io' });
```

## Quick Reference

| Feature | URL Variable | Path |
|---------|-------------|------|
| Chat (Socket.IO) | `NEXT_PUBLIC_NEST_URL` | `/chat` namespace |
| Auth (login, etc.) | `NEXT_PUBLIC_NEST_URL` | `/api/v1/auth/*` |
| Chat Sessions | `NEXT_PUBLIC_NEST_URL` | `/api/v1/chat/*` |
| User Profile | `NEXT_PUBLIC_NEST_URL` | `/api/v1/users/*` |
| RAG/Embeddings | `NEXT_PUBLIC_API_URL` | varies (Python) |

## Deployment Checklist

### Vercel (Frontend)

- [ ] Set `NEXT_PUBLIC_NEST_URL` to your Render Gateway URL
- [ ] Do NOT include `/api/v1` or trailing slash
- [ ] Set `NEXT_PUBLIC_API_URL` only if using Python features

### Render (Gateway)

- [ ] Set `FRONTEND_URL` to exact Vercel domain(s)
- [ ] Include `https://` scheme
- [ ] Multiple domains: comma-separated
- [ ] Set `GEMINI_API_KEY` for chat
- [ ] Set `AI_SERVICES_URL` only if gateway needs to call Python

### Railway (Python Services) - Optional

- [ ] Only deploy if using Python-specific features
- [ ] Not required for basic chat functionality
