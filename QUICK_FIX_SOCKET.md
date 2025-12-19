# Quick Fix: Socket.IO Connection

## The Issue
Frontend was connecting to wrong backend service (Python instead of Gateway), causing timeouts.

## The Fix - 3 Steps

### 1️⃣ Add Vercel Environment Variable
```
NEXT_PUBLIC_NEST_URL=https://intellimaint-ai-backend.onrender.com
```

### 2️⃣ Update Frontend Socket.IO Code
```ts
// Change from:
const socket = io(process.env.NEXT_PUBLIC_API_URL + '/chat');

// To:
const socket = io(process.env.NEXT_PUBLIC_NEST_URL + '/chat', {
  path: '/socket.io',
  transports: ['websocket'],
  withCredentials: true,
});
```

### 3️⃣ Redeploy & Test
- Deploy frontend to Vercel
- Open browser DevTools → Network tab
- Look for `wss://...onrender.com/socket.io/?EIO=4&transport=websocket`
- Should show `101 Switching Protocols` ✅

## What Changed on Backend
- ✅ Socket.IO now uses websocket-only (no polling issues)
- ✅ Increased timeouts for Render cold starts (45s)
- ✅ CORS properly configured for Vercel domains

## Remember
- `NEXT_PUBLIC_NEST_URL` → Gateway (Socket.IO, /api/v1/*)
- `NEXT_PUBLIC_API_URL` → Python services (optional, not for chat)

## Full Details
See [SOCKET_TIMEOUT_FIX.md](SOCKET_TIMEOUT_FIX.md) and [ENV_VARIABLES_GUIDE.md](ENV_VARIABLES_GUIDE.md)
