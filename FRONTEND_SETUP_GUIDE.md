# Frontend API Configuration Guide

This guide will help you update your frontend to connect to the deployed backend on Render.

## Backend URL

Your backend is deployed at: **`https://your-app-name.onrender.com`** (check your Render dashboard for the exact URL)

## Step 1: Update Frontend Environment Variables

### For Next.js Projects:

1. **Create or update `.env.production`** in your frontend repository:
```bash
NEXT_PUBLIC_API_URL=https://your-app-name.onrender.com
```

2. **Update `.env.local` for local development** (optional):
```bash
NEXT_PUBLIC_API_URL=http://localhost:3000
```

3. **Set in Vercel Dashboard:**
   - Go to your Vercel project → Settings → Environment Variables
   - Add: `NEXT_PUBLIC_API_URL` = `https://your-app-name.onrender.com`
   - Apply to: Production, Preview, Development

### For React/Vite Projects:

1. **Create or update `.env.production`:**
```bash
VITE_API_URL=https://your-app-name.onrender.com
```

2. **Set in Vercel Dashboard:**
   - Add: `VITE_API_URL` = `https://your-app-name.onrender.com`

### For React (Create React App):

1. **Create or update `.env.production`:**
```bash
REACT_APP_API_URL=https://your-app-name.onrender.com
```

2. **Set in Vercel Dashboard:**
   - Add: `REACT_APP_API_URL` = `https://your-app-name.onrender.com`

## Step 2: Update API Client Configuration

Find your API client file (usually in `src/api/`, `src/lib/`, `src/utils/`, or `src/config/`):

### Example for Axios:

**Before:**
```typescript
const apiClient = axios.create({
  baseURL: 'http://localhost:3000/api/v1',
});
```

**After:**
```typescript
const apiClient = axios.create({
  baseURL: `${process.env.NEXT_PUBLIC_API_URL || process.env.VITE_API_URL || process.env.REACT_APP_API_URL || 'http://localhost:3000'}/api/v1`,
  withCredentials: true, // Important for cookies
});
```

### Example for Fetch:

**Before:**
```typescript
fetch('http://localhost:3000/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});
```

**After:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.VITE_API_URL || process.env.REACT_APP_API_URL || 'http://localhost:3000';

fetch(`${API_URL}/api/v1/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include', // Important for cookies
  body: JSON.stringify(data),
});
```

## Step 3: Search and Replace in Your Frontend Code

Run these commands in your frontend repository to find all instances:

```bash
# Find all localhost:3000 references
grep -r "localhost:3000" src/
grep -r "http://localhost" src/

# Find environment variable usage
grep -r "process.env" src/
grep -r "import.meta.env" src/  # For Vite
```

## Step 4: Common Files to Check

Look for these common patterns in your frontend:

1. **API client/utility files:**
   - `src/api/client.ts`
   - `src/utils/api.ts`
   - `src/config/api.ts`
   - `src/services/api.ts`
   - `src/lib/api.ts`

2. **Environment files:**
   - `.env`
   - `.env.local`
   - `.env.production`
   - `.env.development`

3. **Configuration files:**
   - `next.config.js` (Next.js)
   - `vite.config.ts` (Vite)
   - `config.json`

## Step 5: Quick Fix - Direct Search and Replace

If you have hardcoded URLs, you can do a global replace:

**Find:** `http://localhost:3000`
**Replace with:** `process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3000'` (or your env var name)

## Step 6: Verify Configuration

After updating:

1. **Rebuild your frontend:**
   ```bash
   npm run build
   ```

2. **Redeploy to Vercel:**
   - Push your changes to git
   - Vercel will auto-deploy, OR
   - Manually trigger a deployment in Vercel dashboard

3. **Test the connection:**
   - Open browser DevTools → Network tab
   - Try logging in
   - Verify requests go to your Render backend URL (not localhost)

## Troubleshooting

### CORS Errors:
- Ensure your Render backend has `FRONTEND_URL` environment variable set to your Vercel domain
- Check that `https://intellimaint-ai.vercel.app` is in the allowed origins

### Cookies Not Working:
- Ensure `credentials: 'include'` (fetch) or `withCredentials: true` (axios) is set
- Check that CORS is configured with `credentials: true` on backend

### Environment Variables Not Working:
- For Next.js: Variables must start with `NEXT_PUBLIC_`
- For Vite: Variables must start with `VITE_`
- For CRA: Variables must start with `REACT_APP_`
- Rebuild after changing environment variables
- Clear browser cache and hard refresh

## Need Help?

1. Check browser console for specific error messages
2. Check Network tab to see what URL is being called
3. Verify Render backend is running and accessible
4. Check Render logs for CORS-related errors

