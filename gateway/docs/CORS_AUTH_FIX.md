# CORS Authentication Fix Guide

## Problem Summary
CORS errors were occurring during login on production server while working fine on localhost. This was caused by improper cookie configuration for cross-origin requests.

## Root Causes Identified

### 1. **SameSite Cookie Policy**
- **Before**: `sameSite: 'lax'` (default)
- **Issue**: `lax` mode blocks cookies in cross-origin POST requests from being sent with credentials
- **Solution**: Use `sameSite: 'none'` for production (requires `secure: true`)

### 2. **Secure Flag Inconsistency**
- **Before**: Only set to `true` when `NODE_ENV === 'production'`
- **Issue**: Production servers often don't expose NODE_ENV or it's misconfigured
- **Solution**: Added `FORCE_SECURE_COOKIES` env variable as override

### 3. **CORS Configuration Missing Explicit Options**
- **Before**: Only had `origin` and `credentials`
- **Issue**: Browser preflight requests weren't properly configured
- **Solution**: Added explicit methods, headers, and maxAge

## Changes Made

### 1. **main.ts** - Enhanced CORS Configuration
```typescript
app.enableCors({
  origin: allowedOrigins,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  exposedHeaders: ['Content-Type', 'X-Total-Count'],
  maxAge: 3600,
});
```

### 2. **All Cookie Settings** Updated across:
- `auth.service.ts` - Login endpoint
- `auth.controller.ts` - Google redirect, logout, and error handling

**New Cookie Configuration:**
```typescript
res.cookie('cookie_name', value, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
    sameSite: process.env.NODE_ENV === 'production' ? 'none' : 'lax',
    path: '/',
    maxAge: <duration>,
});
```

## Environment Variables Required

### Required for Production
```bash
# Your existing variables
NODE_ENV=production
FRONTEND_URL=https://yourdomain.com

# NEW - Override for secure cookies (if NODE_ENV not set properly)
FORCE_SECURE_COOKIES=true
```

### Development (Local)
```bash
NODE_ENV=development
FRONTEND_URL=http://localhost:3001
# FORCE_SECURE_COOKIES not needed
```

## How It Works

### On Localhost (Development)
- `sameSite: 'lax'` - Allows cookies for same-site requests
- `secure: false` - Allows HTTP connections
- Cookies work normally with local development

### On Production Server (Cross-Origin)
- `sameSite: 'none'` - Required for cross-origin cookies (must pair with `secure: true`)
- `secure: true` - HTTPS only (required by browser spec when `sameSite: 'none'`)
- Browser will now send cookies with cross-origin POST requests

## SameSite Policy Explanation

| SameSite Value | Same-Site Requests | Cross-Site Requests |
|---|---|---|
| `lax` | ✅ Sent | ❌ Blocked (POST) |
| `strict` | ✅ Sent | ❌ Blocked (All) |
| `none` | ✅ Sent | ✅ Sent (if `secure: true`) |

## Testing Your Fix

### 1. **Test Login on Production**
```bash
curl -X POST https://your-api.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Origin: https://yourdomain.com" \
  -c cookies.txt \
  -d '{"email":"user@example.com","password":"password"}'
```

### 2. **Verify CORS Preflight**
```bash
curl -X OPTIONS https://your-api.com/api/v1/auth/login \
  -H "Origin: https://yourdomain.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"
```

Should return `Access-Control-Allow-*` headers.

### 3. **Check Cookie Headers**
Look for `Set-Cookie` headers with:
- `SameSite=None`
- `Secure`
- `HttpOnly`

## Frontend Implementation

Your frontend should already have credentials enabled:

```typescript
// Good - For axios
axios.create({
  withCredentials: true,
  baseURL: 'https://your-api.com'
});

// Good - For fetch
fetch('https://your-api.com/api/v1/auth/login', {
  method: 'POST',
  credentials: 'include',  // This is crucial
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({...})
});

// Good - For React Query
useQuery({
  queryFn: async () => {
    const res = await fetch(..., { 
      credentials: 'include' 
    });
    return res.json();
  }
});
```

## Common Issues & Solutions

### Issue: "Cookie not sent with request"
**Solution**: 
- Ensure `credentials: 'include'` on frontend
- Check `FRONTEND_URL` is exact match (protocol + domain)
- Verify HTTPS on production with `secure: true`

### Issue: "CORS error but GET requests work"
**Solution**:
- Check `sameSite` is set to `'none'` for production
- Verify `secure: true` is enabled
- Check `methods` array includes `POST`

### Issue: "Cookie cleared/not persisting"
**Solution**:
- Verify all clear cookie operations also use `sameSite: 'none'` and `secure: true`
- Check cookie `path: '/'` matches across all operations

## Deployment Checklist

- [ ] Set `NODE_ENV=production` on server
- [ ] Set `FRONTEND_URL` to your exact frontend domain
- [ ] Enable HTTPS (required for `sameSite: 'none'`)
- [ ] If NODE_ENV not working, set `FORCE_SECURE_COOKIES=true`
- [ ] Test login flow end-to-end
- [ ] Check browser console for CORS errors
- [ ] Verify cookies appear in Application tab with correct flags
- [ ] Test refresh token flow
- [ ] Test logout (cookies cleared)

## References

- [MDN: SameSite Cookie Attribute](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite)
- [CORS with Credentials](https://developer.mozilla.org/en-US/docs/Web/API/fetch#:~:text=credentials)
- [NestJS CORS Documentation](https://docs.nestjs.com/security/cors)
