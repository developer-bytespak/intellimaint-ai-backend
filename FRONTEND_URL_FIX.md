# Frontend API URL Fix

## Critical Issues Fixed

### 1. ✅ Backend CORS Configuration
The backend now properly allows requests from `https://intellimaint-ai.vercel.app`.

### 2. ✅ Cookie Settings for Cross-Domain
Updated cookie settings to work with cross-domain (Vercel ↔ Render):
- `sameSite: 'none'` in production
- `secure: true` in production
- Proper domain handling

## Frontend Changes Required

### ❌ Current (Wrong) URL:
```
https://intellimaint-ai-backend.onrender.com/auth/login
```

### ✅ Correct URL:
```
https://intellimaint-ai-backend.onrender.com/api/v1/auth/login
```

**Notice the `/api/v1` prefix!**

## Steps to Fix in Your Frontend

### 1. Check Your Environment Variable
Make sure your Vercel environment variable is:
```
NEXT_PUBLIC_API_URL=https://intellimaint-ai-backend.onrender.com
```
(without the `/api/v1` suffix - that's added in code)

### 2. Update Your API Client Code

Find where you're making the login request and ensure it uses the full path:

**✅ Correct:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3000';
fetch(`${API_URL}/api/v1/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include', // IMPORTANT for cookies!
  body: JSON.stringify({ email, password }),
});
```

**❌ Wrong:**
```typescript
fetch(`${API_URL}/auth/login`, { ... }); // Missing /api/v1
```

### 3. Handle the Response

The login response now includes user data:
```typescript
{
  status: 200,
  message: "Login successful",
  data: {
    user: { ... },
    accessToken: "..."
  }
}
```

After successful login, your frontend should:
1. Check the response status
2. Redirect to `/chat` or handle the user data
3. Cookies are automatically set (with `credentials: 'include'`)

### 4. Verify in Browser DevTools

After deploying, check:
1. **Network tab**: Request should go to `...onrender.com/api/v1/auth/login`
2. **Response**: Should have status 200 with user data
3. **Cookies**: Should see `local_access` cookie set (in Application/Storage tab)
4. **CORS**: Should see proper CORS headers in response

## Common Issues

### Issue: "Login successful but no redirect"
**Solution**: Check your frontend code that handles the login response. Make sure:
- You're checking the response status correctly
- You're calling `router.push('/chat')` or similar after success
- There are no errors in the console

### Issue: "CORS error"
**Solution**: 
- Make sure `FRONTEND_URL` in Render includes `https://intellimaint-ai.vercel.app`
- Backend now auto-adds this, but double-check Render environment variables
- Redeploy backend after changes

### Issue: "Cookies not working"
**Solution**:
- Ensure `credentials: 'include'` is set in fetch/axios
- Check that `secure: true` cookies work (requires HTTPS)
- Verify browser allows third-party cookies (for cross-domain)

## Testing Checklist

- [ ] API URL includes `/api/v1` prefix
- [ ] Environment variable set in Vercel
- [ ] `credentials: 'include'` in fetch/axios requests
- [ ] Frontend redirects after successful login
- [ ] Cookies visible in browser DevTools
- [ ] No CORS errors in console
- [ ] Backend logs show the request
