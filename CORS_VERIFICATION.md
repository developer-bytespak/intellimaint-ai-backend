# CORS and Cookie Verification Guide

## What Has Been Fixed

### 1. ✅ CORS Configuration
- Added `HEAD` method to allowed methods
- Exact origin matching (not `*`)
- Proper preflight handling
- All required headers configured

### 2. ✅ Cookie Settings
- `HttpOnly: true` ✅
- `SameSite: 'none'` in production ✅
- `Secure: true` in production ✅
- Proper domain/path settings ✅

## Required Headers (All Set)

### OPTIONS Preflight Response:
- ✅ `Access-Control-Allow-Origin: https://intellimaint-ai.vercel.app` (exact match)
- ✅ `Access-Control-Allow-Credentials: true`
- ✅ `Access-Control-Allow-Methods: GET,HEAD,PUT,PATCH,POST,DELETE,OPTIONS`
- ✅ `Access-Control-Allow-Headers: Content-Type,Authorization,Accept`

### POST Login Response:
- ✅ `Access-Control-Allow-Origin: https://intellimaint-ai.vercel.app`
- ✅ `Access-Control-Allow-Credentials: true`
- ✅ `Set-Cookie: local_access=...; HttpOnly; Secure; SameSite=None`
- ✅ `Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=None`

## Verification Steps

### 1. Deploy Backend
Push and deploy the updated backend to Render.

### 2. Browser DevTools Verification

**In Chrome/Edge DevTools:**

1. Open your Vercel site: `https://intellimaint-ai.vercel.app`
2. Open DevTools (F12) → Network tab
3. Check "Preserve log"
4. Attempt login
5. Look for:
   - **OPTIONS request** to `/api/v1/auth/login`
   - **POST request** to `/api/v1/auth/login`

**Check OPTIONS Response Headers:**
```
Access-Control-Allow-Origin: https://intellimaint-ai.vercel.app
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,HEAD,PUT,PATCH,POST,DELETE,OPTIONS
Access-Control-Allow-Headers: Content-Type,Authorization,Accept
```

**Check POST Response Headers:**
```
Access-Control-Allow-Origin: https://intellimaint-ai.vercel.app
Access-Control-Allow-Credentials: true
Set-Cookie: local_access=...; HttpOnly; Secure; SameSite=None; Path=/
Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=None; Path=/
```

**Check Cookies:**
1. DevTools → Application tab → Cookies
2. Should see cookies under both:
   - `https://intellimaint-ai.vercel.app` (if stored client-side)
   - `https://intellimaint-ai-backend.onrender.com` (server-set cookies)

### 3. cURL Verification

**Test Preflight (OPTIONS):**
```bash
curl -X OPTIONS \
  https://intellimaint-ai-backend.onrender.com/api/v1/auth/login \
  -H "Origin: https://intellimaint-ai.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -v
```

**Expected output should include:**
```
< Access-Control-Allow-Origin: https://intellimaint-ai.vercel.app
< Access-Control-Allow-Credentials: true
< Access-Control-Allow-Methods: GET,HEAD,PUT,PATCH,POST,DELETE,OPTIONS
< Access-Control-Allow-Headers: Content-Type,Authorization,Accept
```

**Test Login (POST):**
```bash
curl -X POST \
  https://intellimaint-ai-backend.onrender.com/api/v1/auth/login \
  -H "Origin: https://intellimaint-ai.vercel.app" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}' \
  -v -c cookies.txt
```

**Check response headers:**
```
< Access-Control-Allow-Origin: https://intellimaint-ai.vercel.app
< Access-Control-Allow-Credentials: true
< Set-Cookie: local_access=...; HttpOnly; Secure; SameSite=None; Path=/
```

### 4. Common Issues & Solutions

#### Issue: Still getting CORS errors
**Check:**
- Render environment variable `FRONTEND_URL` includes `https://intellimaint-ai.vercel.app`
- Backend is redeployed after changes
- Browser cache cleared (try incognito)
- Exact origin match (no trailing slashes)

#### Issue: Cookies not being set
**Check:**
- `credentials: 'include'` in frontend fetch/axios
- HTTPS on both domains (required for `Secure` cookies)
- Browser allows third-party cookies (for cross-domain)
- Response shows `Set-Cookie` header in Network tab

#### Issue: SameSite=None not working
**Requirements:**
- Must use `Secure: true` (requires HTTPS)
- Both domains must use HTTPS
- Browser must support SameSite=None (modern browsers do)

### 5. Production Environment Variables

**In Render Dashboard, ensure:**
```
NODE_ENV=production
FRONTEND_URL=https://intellimaint-ai.vercel.app
```

**In Vercel Dashboard:**
```
NEXT_PUBLIC_API_URL=https://intellimaint-ai-backend.onrender.com
```

### 6. Frontend Code Requirements

**Must include in all API requests:**
```typescript
fetch(`${API_URL}/api/v1/auth/login`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  credentials: 'include', // CRITICAL for cookies
  body: JSON.stringify({ email, password }),
});
```

**For Axios:**
```typescript
axios.defaults.withCredentials = true;
```

## Success Criteria

✅ No CORS errors in console
✅ OPTIONS request returns 204/200 with proper headers
✅ POST request succeeds (200 status)
✅ Cookies visible in DevTools → Application → Cookies
✅ Cookies sent with subsequent requests
✅ User redirected to chat page after login

## Debugging

If issues persist, check Render logs:
1. Go to Render dashboard
2. Select your backend service
3. View logs for:
   - `Allowed CORS origins: [...]`
   - Any `CORS blocked origin:` warnings
   - Login request logs
