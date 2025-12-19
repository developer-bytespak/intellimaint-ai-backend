# Safari Third-Party Cookie Issue - SOLVED ✅

## Problem

Safari (especially on iOS) **blocks third-party cookies by default**. Since your:
- Frontend: `intellimaint-ai.vercel.app`
- Backend: `intellimaint-ai-backend.onrender.com`

are on **different domains**, Safari treats backend cookies as third-party and blocks them.

## What We Fixed in Backend

### ✅ Backend Now Returns Tokens in Response Body

The login endpoint now returns:
```json
{
  "status": 200,
  "message": "Login successful",
  "data": {
    "user": { ... },
    "accessToken": "eyJhbGc...",
    "refreshToken": "eyJhbGc...",
    "expiresIn": 3600
  }
}
```

### ✅ Backend Accepts Tokens from Authorization Header

The authentication guard now checks tokens in this order:
1. **Authorization: Bearer <token>** header (NEW!)
2. Cookie: `local_accessToken`
3. Cookie: `google_accessToken`

---

## Frontend Implementation Guide

### Step 1: Update Login Handler

```typescript
// Login function
async function login(email: string, password: string) {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // Still try cookies first
    body: JSON.stringify({ email, password }),
  });

  const result = await response.json();

  if (result.status === 200) {
    const { accessToken, refreshToken, user, expiresIn } = result.data;
    
    // Store tokens in localStorage (fallback for Safari)
    localStorage.setItem('accessToken', accessToken);
    localStorage.setItem('refreshToken', refreshToken);
    localStorage.setItem('user', JSON.stringify(user));
    localStorage.setItem('tokenExpiry', Date.now() + (expiresIn * 1000));
    
    // Redirect to chat
    router.push('/chat');
  }
}
```

### Step 2: Create API Client with Token Header

```typescript
// lib/api-client.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export async function apiRequest(endpoint: string, options: RequestInit = {}) {
  const token = localStorage.getItem('accessToken');
  
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  // Add Authorization header if token exists
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include', // Still include for browsers that support cookies
  });

  // If 401, try to refresh token
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry request with new token
      headers['Authorization'] = `Bearer ${localStorage.getItem('accessToken')}`;
      return fetch(`${API_URL}${endpoint}`, { ...options, headers, credentials: 'include' });
    }
    // Refresh failed, redirect to login
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  return response;
}

// Refresh token function
async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refreshToken');
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${refreshToken}`
      },
      credentials: 'include',
    });

    if (response.ok) {
      const result = await response.json();
      localStorage.setItem('accessToken', result.data.accessToken);
      localStorage.setItem('tokenExpiry', Date.now() + (result.data.expiresIn * 1000));
      return true;
    }
  } catch (error) {
    console.error('Token refresh failed:', error);
  }

  return false;
}
```

### Step 3: Update All API Calls

```typescript
// Before (old way)
fetch(`${API_URL}/api/v1/chat/sessions`, {
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
});

// After (new way)
import { apiRequest } from '@/lib/api-client';

apiRequest('/api/v1/chat/sessions', {
  method: 'GET',
});
```

### Step 4: Update Middleware for Auth Check

```typescript
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  // Check if user has token in cookies OR localStorage would be checked client-side
  const token = request.cookies.get('local_accessToken')?.value;
  
  const isAuthPage = request.nextUrl.pathname.startsWith('/login') || 
                     request.nextUrl.pathname.startsWith('/register');
  const isProtectedPage = request.nextUrl.pathname.startsWith('/chat') ||
                          request.nextUrl.pathname.startsWith('/dashboard');

  // If no cookie, we can't check localStorage here (server-side)
  // So we'll let the page load and check client-side
  if (!token && isProtectedPage) {
    // Redirect to login, but add a return URL
    const url = new URL('/login', request.url);
    url.searchParams.set('returnUrl', request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }

  if (token && isAuthPage) {
    return NextResponse.redirect(new URL('/chat', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
```

### Step 5: Client-Side Auth Check (Layout or Protected Pages)

```typescript
// app/chat/layout.tsx or useEffect in protected pages
'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function ChatLayout({ children }) {
  const router = useRouter();

  useEffect(() => {
    // Check if user is authenticated
    const token = localStorage.getItem('accessToken');
    const expiry = localStorage.getItem('tokenExpiry');

    if (!token || (expiry && Date.now() > parseInt(expiry))) {
      // No token or expired
      router.push('/login');
    }
  }, [router]);

  return <>{children}</>;
}
```

### Step 6: Logout Function

```typescript
async function logout() {
  // Clear localStorage
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('user');
  localStorage.removeItem('tokenExpiry');

  // Call backend logout endpoint (clears cookies if they exist)
  try {
    await fetch(`${API_URL}/api/v1/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch (error) {
    console.error('Logout error:', error);
  }

  // Redirect to login
  router.push('/login');
}
```

---

## Testing Checklist

- [ ] Login returns tokens in response body
- [ ] Tokens stored in localStorage
- [ ] API requests include `Authorization: Bearer <token>` header
- [ ] Protected routes check for token
- [ ] Token refresh works when access token expires
- [ ] Logout clears localStorage
- [ ] Works in Safari on iOS
- [ ] Works in Chrome/Firefox (with cookies as backup)

---

## Security Notes

⚠️ **localStorage is less secure than HttpOnly cookies** because:
- Accessible via JavaScript (vulnerable to XSS attacks)
- Persists across tabs/windows

✅ **Mitigations:**
1. Implement Content Security Policy (CSP)
2. Sanitize all user inputs
3. Use short token expiration times (1 hour for access token)
4. Implement refresh token rotation
5. Add logout on suspicious activity

---

## Alternative: Use Same-Domain Setup (More Secure)

For better security, deploy backend to a subdomain:
- Frontend: `intellimaint.com`
- Backend: `api.intellimaint.com`

Then cookies work as first-party! 🎉
