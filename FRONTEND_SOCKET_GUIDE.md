# Frontend Socket.IO Setup (Vercel)

Use these settings to connect from your Next.js/Vercel frontend to the Render-hosted gateway.

## Environment Variables

**IMPORTANT:** The chat system runs entirely in the NestJS Gateway (not the Python services):

- **`NEXT_PUBLIC_NEST_URL`** - Points to the NestJS Gateway on Render (e.g., `https://intellimaint-ai-backend.onrender.com`)
  - Use this for Socket.IO connections and all `/api/v1/*` endpoints
- **`NEXT_PUBLIC_API_URL`** - Points to Python services (optional, only if using Python-specific endpoints)

## Socket.IO Configuration

- Socket namespace: `/chat`
- Socket path: `/socket.io`
- Transports: `['websocket']` (avoid polling to prevent Render sticky-session issues)
- Credentials: `withCredentials: true` for cookie-based auth

## Example Code (socket.io-client v4)

```ts
import { io } from 'socket.io-client';

// Use NEXT_PUBLIC_NEST_URL for the Gateway (where Socket.IO and chat run)
const NEST_URL = process.env.NEXT_PUBLIC_NEST_URL!; // e.g. https://intellimaint-ai-backend.onrender.com

// Connect to the /chat namespace
export const socket = io(`${NEST_URL}/chat`, {
  path: '/socket.io',
  transports: ['websocket'], // Force websocket-only for Render
  withCredentials: true, // Include cookies for authentication
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  timeout: 20000,
  extraHeaders: {
    // If you use header-based auth (JWT), add here:
    // Authorization: `Bearer ${token}`,
  },
});

socket.on('connect', () => {
  console.log('✅ Socket connected:', socket.id);
});

socket.on('connect_error', (err) => {
  console.error('❌ Socket connect error:', err?.message, err);
});

socket.on('disconnect', (reason) => {
  console.log('🔌 Socket disconnected:', reason);
});
```

## Important Notes

1. **Path:** Do NOT prefix the Socket.IO path with `/api/v1`. The Socket.IO engine uses `/socket.io` at the root, while HTTP REST APIs use `/api/v1/*`.

2. **Chat Implementation:** The entire chat system (including Gemini AI integration) runs in the NestJS Gateway using `GeminiChatService`. No Python services are involved.

3. **Render Deployment:** 
   - If you scale to multiple instances and use polling transports, enable sticky sessions in Render
   - We force `websocket`-only to avoid this requirement
   - Make sure `FRONTEND_URL` on Render exactly matches your Vercel domain(s)

4. **Multiple Frontends:** If you have multiple frontend domains, set `FRONTEND_URL` as comma-separated on Render:
   ```
   FRONTEND_URL=https://app.vercel.app,https://staging.vercel.app
   ```
