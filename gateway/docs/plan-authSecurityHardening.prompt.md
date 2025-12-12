# Authentication Security Hardening Plan

## Overview

Your IntelliMaint authentication system has **25 identified vulnerabilities** across 4 severity levels:
- **5 Critical** - Token revocation, rate limiting, password reset, password complexity, OAuth encryption
- **7 High** - Security headers, CSRF, HTTPS enforcement, account lockout, RBAC
- **8 Medium** - OTP encryption, attempt limiting, session management, audit logging
- **5 Low** - Debug logs, type safety, token fingerprinting, best practices

## Phased Implementation Roadmap

### Phase 1: Critical Security Fixes (48 Hours)
**Objective:** Close immediate security holes that enable account takeover

#### 1.1 - Implement Token Revocation on Logout (Stateless Versioning)
**File:** `gateway/src/modules/auth/auth.service.ts`, `gateway/src/common/guards/jwt-auth.guard.ts`
**Current Issue:** Logout only clears cookies; refresh tokens remain valid in database
**Action (Lightweight Approach):**
- Use **token versioning** instead of blacklisting (no database bloat)
- Store only a version number per user in Redis: `token_version:${userId} = 1`
- Include version in JWT payload when generating tokens
- On logout, increment the version in Redis (auto-expires with Redis TTL)
- Guard validates token version matches current version
- No cleanup job needed; Redis auto-expires

**Why this is better than token blacklist:**
- Single integer per user in Redis (not thousands of tokens in DB)
- Auto-expires with Redis TTL (no manual cleanup)
- O(1) lookup on validation
- No database size growth
- Automatically prevents token reuse

**Implementation:**

```typescript
// auth.service.ts - Token generation
async generateTokens(userId: string) {
  // Get current token version from Redis
  const versionKey = `token_version:${userId}`;
  let version = await this.redisService.get(versionKey);
  
  if (!version) {
    // First time - initialize version to 1
    version = 1;
    await this.redisService.set(versionKey, '1', 7 * 24 * 60 * 60); // 7 days
  }
  
  const accessToken = this.jwtService.sign({
    userId,
    version: Number(version),
    type: 'access'
  }, { expiresIn: '1h' });
  
  const refreshToken = this.jwtService.sign({
    userId,
    version: Number(version),
    type: 'refresh'
  }, { expiresIn: '7d' });
  
  return { accessToken, refreshToken };
}

// auth.service.ts - Logout
async logout(userId: string) {
  const versionKey = `token_version:${userId}`;
  
  // Increment version to invalidate all existing tokens
  await this.redisService.incr(versionKey);
  
  // Set expiry to match longest token lifetime
  await this.redisService.expire(versionKey, 7 * 24 * 60 * 60); // 7 days
  
  // Clear cookies
  res.clearCookie('local_access');
  res.clearCookie('refresh_token');
  // ... clear other cookies
}

// jwt-auth.guard.ts - Validation
async canActivate(context: ExecutionContext): Promise<boolean> {
  const token = this.extractTokenFromRequest(request);
  
  if (!token) return false;
  
  try {
    const decoded = this.jwtService.verify(token);
    
    // Check if token version still matches user's current version
    const currentVersion = await this.redisService.get(`token_version:${decoded.userId}`);
    
    if (!currentVersion || Number(currentVersion) !== decoded.version) {
      throw new UnauthorizedException('Token has been revoked');
    }
    
    request.user = decoded;
    return true;
  } catch (error) {
    throw new UnauthorizedException('Invalid token');
  }
}
```

**Benefits:**
- ✅ Prevents token reuse after logout (increment version)
- ✅ Prevents old tokens from being used (version check)
- ✅ No database growth (only Redis integers)
- ✅ Auto-expires with Redis (no cleanup jobs)
- ✅ Supports multiple concurrent refresh tokens per user
- ✅ Can revoke all tokens by incrementing version (forces re-login)

**Frontend Impact:** After logout, subsequent API calls will get 401 even with old refresh token. Frontend should redirect to login.

**Alternative if you want session-based:**
Delete the session record from database instead and check session existence. This is also lightweight but requires a DB lookup.

---

#### 1.2 - Implement Rate Limiting on Auth Endpoints
**File:** `gateway/src/main.ts`, `gateway/src/modules/auth/auth.controller.ts`
**Current Issue:** No rate limiting enables brute force attacks
**Dependencies:** Install `@nestjs/throttler` and `@nestjs/common`
**Action:**
- Install package
- Configure global throttler with 100 requests per 15 minutes
- Apply stricter limits to sensitive endpoints:
  - Login: 5 attempts per 15 minutes per IP
  - Password reset: 3 attempts per 1 hour per email
  - OTP verification: 5 attempts per 10 minutes per email
  - Register: 3 accounts per hour per IP

```typescript
// app.module.ts
import { ThrottlerGuard, ThrottlerModule } from '@nestjs/throttler';

@Module({
  imports: [
    ThrottlerModule.forRoot([
      {
        ttl: 60000,        // 1 minute
        limit: 100,        // 100 requests per minute
      },
    ]),
  ],
  providers: [
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard,
    },
  ],
})
export class AppModule {}
```

**Custom decorator for auth endpoints:**
```typescript
@Post('login')
@Throttle({ default: { limit: 5, ttl: 15 * 60 * 1000 } }) // 5/15min
async login(@Body() body: any) { ... }
```

---

#### 1.3 - Fix Password Reset to Require OTP Verification
**File:** `gateway/src/modules/auth/auth.service.ts`, `gateway/src/modules/auth/auth.controller.ts`
**Current Issue:** Reset password endpoint doesn't verify OTP despite forgot-password sending it
**Action:**
- Add `otp_verifications` table to track which OTPs have been verified
- Modify `resetPassword()` to require `otp` parameter
- Verify OTP against Redis before allowing password reset
- Mark OTP as used (delete from Redis or add to verified set)
- Send confirmation email after password change

```typescript
async resetPassword(email: string, otp: string, newPassword: string) {
  // 1. Verify OTP
  const otpKey = `otp:${email}`;
  const storedOtp = await this.redisService.get(otpKey);
  
  if (!storedOtp || storedOtp !== otp) {
    throw new BadRequestException('Invalid or expired OTP');
  }
  
  // 2. Check password history (don't reuse last 5 passwords)
  const user = await this.prisma.user.findUnique({ where: { email } });
  
  // 3. Update password
  const hashedPassword = await this.hashPassword(newPassword);
  await this.prisma.user.update({
    where: { id: user.id },
    data: { passwordHash: hashedPassword }
  });
  
  // 4. Clean up OTP
  await this.redisService.del(otpKey);
  
  // 5. Invalidate all existing sessions (force re-login)
  await this.prisma.session.deleteMany({ where: { userId: user.id } });
  
  // 6. Send confirmation email
  await this.emailService.sendPasswordChangedNotification(email);
}
```

**Frontend Changes Required:**
- Add OTP input field to password reset form
- Call verify-otp endpoint before calling reset-password with OTP included

---

#### 1.4 - Add Password Complexity Requirements
**File:** `gateway/src/modules/auth/dto/register.dto.ts`
**Current Issue:** Passwords only need 8 characters; "password1" is accepted
**Action:**
- Create password validation service with rules:
  - Minimum 12 characters (raise from 8)
  - Require uppercase letter
  - Require lowercase letter
  - Require number
  - Require special character (!@#$%^&*)
  - Maximum 128 characters
  - Check against common passwords list
  - Cannot contain email or name
  - Cannot be commonly breached password

```typescript
// password-validator.service.ts
export class PasswordValidatorService {
  private commonPasswords = ['password', 'qwerty', '123456', ...]; // Load from file
  
  validate(password: string, userEmail: string, userName: string): ValidationResult {
    const errors = [];
    
    if (password.length < 12) errors.push('Minimum 12 characters required');
    if (password.length > 128) errors.push('Maximum 128 characters allowed');
    if (!/[A-Z]/.test(password)) errors.push('Must contain uppercase letter');
    if (!/[a-z]/.test(password)) errors.push('Must contain lowercase letter');
    if (!/[0-9]/.test(password)) errors.push('Must contain number');
    if (!/[!@#$%^&*]/.test(password)) errors.push('Must contain special character');
    if (this.commonPasswords.includes(password.toLowerCase())) {
      errors.push('Password too common');
    }
    if (password.toLowerCase().includes(userEmail.split('@')[0])) {
      errors.push('Cannot contain email address');
    }
    
    return { isValid: errors.length === 0, errors };
  }
}
```

**Update DTO:**
```typescript
@IsString()
@MinLength(12)
@MaxLength(128)
@Custom(PasswordValidatorService, 'validate')
password: string;
```

---

#### 1.5 - Encrypt OAuth Tokens Before Storage
**File:** `gateway/src/modules/auth/auth.service.ts`, `gateway/prisma/schema.prisma`
**Current Issue:** Google refresh tokens stored in plaintext in database
**Dependencies:** Install `crypto` (built-in)
**Action:**
- Create encryption/decryption service using AES-256-GCM
- Encrypt Google refresh tokens before storing in `OAuthProvider.refreshToken`
- Decrypt when using tokens to refresh access tokens
- Store encryption IV/nonce separately

```typescript
// encryption.service.ts
import * as crypto from 'crypto';

export class EncryptionService {
  private algorithm = 'aes-256-gcm';
  
  encrypt(plaintext: string): { encryptedData: string; iv: string; authTag: string } {
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv(this.algorithm, Buffer.from(process.env.ENCRYPTION_KEY, 'hex'), iv);
    
    let encrypted = cipher.update(plaintext, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    
    const authTag = cipher.getAuthTag();
    
    return {
      encryptedData: encrypted,
      iv: iv.toString('hex'),
      authTag: authTag.toString('hex')
    };
  }
  
  decrypt(encryptedData: string, iv: string, authTag: string): string {
    const decipher = crypto.createDecipheriv(
      this.algorithm,
      Buffer.from(process.env.ENCRYPTION_KEY, 'hex'),
      Buffer.from(iv, 'hex')
    );
    
    decipher.setAuthTag(Buffer.from(authTag, 'hex'));
    
    let decrypted = decipher.update(encryptedData, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  }
}
```

**Update Prisma schema:**
```prisma
model OAuthProvider {
  id              String   @id @default(cuid())
  userId          String
  provider        OAuthProviderType
  providerUserId  String
  
  // Encrypted fields
  refreshToken    String?  // Encrypted
  refreshTokenIv  String?
  refreshTokenTag String?
  
  accessToken     String?
  accessTokenIv   String?
  accessTokenTag  String?
  
  tokenExpiresAt  DateTime
  user            User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  
  @@unique([provider, userId])
}
```

**Frontend Impact:** No direct impact; all encryption/decryption happens on backend

---

#### 1.6 - Validate JWT_SECRET at Application Startup
**File:** `gateway/src/main.ts`, `gateway/src/config/app.config.ts`
**Current Issue:** JWT_SECRET could be undefined or too short
**Action:**
- Check JWT_SECRET exists and minimum 32 characters
- Check ENCRYPTION_KEY exists and correct length for AES-256 (64 hex characters)
- Check other critical environment variables
- Throw error if validation fails (application won't start)

```typescript
// main.ts
async function bootstrap() {
  // Validate critical config
  const requiredEnvVars = ['JWT_SECRET', 'ENCRYPTION_KEY', 'DATABASE_URL'];
  for (const envVar of requiredEnvVars) {
    if (!process.env[envVar]) {
      throw new Error(`Missing required environment variable: ${envVar}`);
    }
  }
  
  if (process.env.JWT_SECRET.length < 32) {
    throw new Error('JWT_SECRET must be at least 32 characters long');
  }
  
  if (process.env.ENCRYPTION_KEY.length !== 64) {
    throw new Error('ENCRYPTION_KEY must be 64 hex characters (32 bytes for AES-256)');
  }
  
  // ... rest of bootstrap
}
```

**Generate ENCRYPTION_KEY if needed:**
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

---

### Phase 2: Security Headers & CSRF Protection (1 Week)

#### 2.1 - Add Helmet Security Headers
**File:** `gateway/src/main.ts`
**Dependencies:** Install `@nestjs/helmet`
**Action:**
- Install and configure Helmet middleware
- Enables: HSTS, X-Content-Type-Options, X-Frame-Options, CSP, X-XSS-Protection, etc.

```typescript
// main.ts
import helmet from '@nestjs/helmet';

app.use(helmet({
  hsts: {
    maxAge: 31536000, // 1 year
    includeSubDomains: true,
    preload: true
  },
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      scriptSrc: ["'self'"],
      imgSrc: ["'self'", 'data:', 'https:'],
    },
  },
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
}));
```

---

#### 2.2 - Implement CSRF Protection
**File:** `gateway/src/main.ts`, `gateway/src/modules/auth/auth.controller.ts`
**Dependencies:** Install `csurf` and create middleware
**Action:**
- Generate CSRF tokens on every GET request (forms, page loads)
- Validate CSRF tokens on POST/PUT/DELETE/PATCH requests
- Store CSRF token in memory or Redis with session ID

```typescript
// csrf.middleware.ts
import { csrf } from 'csurf';

export const csrfProtection = csrf({
  cookie: false, // Use session/header instead of cookie
  value: (req) => req.body._csrf || req.headers['x-csrf-token'] || req.query._csrf,
});

// In controller
@Post('login')
async login(@Body() body: any, @Req() req: Request) {
  // Verify CSRF token was validated by middleware
  // Middleware throws error if invalid
  return this.authService.login(body, res);
}

// Provide CSRF token on form pages
@Get('login')
getLoginPage(@Req() req: Request, @Res() res: Response) {
  const csrfToken = req.csrfToken?.();
  res.send(`
    <form method="post" action="/auth/login">
      <input type="hidden" name="_csrf" value="${csrfToken}" />
      ...
    </form>
  `);
}
```

**Frontend Changes Required:**
- On form render, include CSRF token in hidden input
- On AJAX requests, include CSRF token in `X-CSRF-Token` header
- Store CSRF token in memory (not localStorage) from page load

---

#### 2.3 - Enforce HTTPS and Secure Cookies
**File:** `gateway/src/main.ts`, `gateway/src/config/app.config.ts`
**Current Issue:** Secure flag only set if NODE_ENV === 'production'; no HTTPS redirect
**Action:**
- Add HTTPS redirect middleware
- Validate NODE_ENV is set correctly
- Use strict secure flag on cookies
- Add trust proxy configuration for reverse proxies

```typescript
// main.ts
app.use((req, res, next) => {
  if (process.env.NODE_ENV === 'production' && !req.secure) {
    return res.redirect(301, `https://${req.headers.host}${req.url}`);
  }
  next();
});

app.set('trust proxy', 1); // Trust first proxy (load balancer)

// All cookie configurations
const cookieConfig = {
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'strict' as const,
  path: '/',
};
```

---

#### 2.4 - Move Email from Non-httpOnly Cookie
**File:** `gateway/src/modules/auth/auth.service.ts`
**Current Issue:** `google_user_email` cookie accessible to JavaScript
**Action:**
- Remove non-httpOnly email cookie
- Store encrypted email in httpOnly cookie
- Decrypt email on server using session data
- Guards read email from session/JWT, not cookie

```typescript
// Before (vulnerable)
res.cookie('google_user_email', user.email, {
  httpOnly: false,  // ❌ Vulnerable
});

// After (secure)
// Store encrypted email in httpOnly cookie OR use JWT claim
res.cookie('google_session_id', sessionId, {
  httpOnly: true,
  secure: true,
  sameSite: 'strict'
});

// JWT includes email claim (it's already in JWT!)
// No need for separate email cookie
```

---

#### 2.5 - Implement Account Lockout After Failed Attempts
**File:** `gateway/src/modules/auth/auth.service.ts`
**Current Issue:** Unlimited login attempts possible
**Action:**
- Track failed login attempts per email in Redis
- Lock account for 15 minutes after 5 failed attempts
- Clear counter on successful login
- Alert user via email when account is locked

```typescript
async login(email: string, password: string) {
  const lockKey = `login_lock:${email}`;
  const attemptsKey = `login_attempts:${email}`;
  
  // Check if account is locked
  const isLocked = await this.redisService.get(lockKey);
  if (isLocked) {
    throw new TooManyRequestsException('Account locked. Try again after 15 minutes.');
  }
  
  // Verify credentials
  const user = await this.prisma.user.findUnique({ where: { email } });
  if (!user || !await bcrypt.compare(password, user.passwordHash)) {
    // Increment failed attempts
    const attempts = await this.redisService.incr(attemptsKey);
    await this.redisService.expire(attemptsKey, 900); // 15 min expiry
    
    if (attempts >= 5) {
      await this.redisService.set(lockKey, '1', 900); // Lock for 15 min
      await this.emailService.sendAccountLockedAlert(email);
      throw new TooManyRequestsException('Too many failed attempts. Account locked.');
    }
    
    throw new UnauthorizedException('Invalid credentials');
  }
  
  // Clear attempts on successful login
  await this.redisService.del(attemptsKey);
  await this.redisService.del(lockKey);
  
  // ... generate tokens
}
```

**Frontend Changes Required:**
- Display message when account is locked
- Disable login form for 15 minutes
- Show countdown timer
- Offer "Unlock via email" option

---

### Phase 3: Advanced Authentication Features (2 Weeks)

#### 3.1 - Encrypt OTPs in Redis
**File:** `gateway/src/modules/auth/auth.service.ts`
**Current Issue:** OTPs stored in plaintext in Redis
**Action:**
- Use same EncryptionService from Phase 1.5
- Encrypt OTP before storing in Redis
- Decrypt and verify on OTP verification endpoint

```typescript
async sendOtp(email: string) {
  const otp = this.generateOTP(); // 6 digits
  const encryptedOtp = this.encryptionService.encrypt(otp);
  
  // Store encrypted OTP
  const otpKey = `otp:${email}`;
  await this.redisService.set(otpKey, JSON.stringify(encryptedOtp), 300); // 5 min
  
  // Send OTP via email
  await this.emailService.sendOtp(email, otp);
}

async verifyOtp(email: string, otp: string) {
  const otpKey = `otp:${email}`;
  const encryptedOtp = await this.redisService.get(otpKey);
  
  if (!encryptedOtp) {
    throw new BadRequestException('OTP expired or not found');
  }
  
  const decryptedOtp = this.encryptionService.decrypt(JSON.parse(encryptedOtp));
  
  if (decryptedOtp !== otp) {
    throw new BadRequestException('Invalid OTP');
  }
  
  // Mark as verified and delete
  await this.redisService.del(otpKey);
  return true;
}
```

---

#### 3.2 - Implement OTP Attempt Limiting
**File:** `gateway/src/modules/auth/auth.service.ts`
**Current Issue:** 6-digit OTP can be brute-forced (1 million combinations)
**Action:**
- Track OTP verification attempts per email
- Allow 3 attempts per OTP
- Require new OTP after 3 failed attempts
- Implement exponential backoff

```typescript
async verifyOtp(email: string, otp: string) {
  const attemptKey = `otp_attempts:${email}`;
  const attempts = await this.redisService.get(attemptKey);
  
  if (attempts >= 3) {
    throw new TooManyRequestsException('OTP attempts exceeded. Request new OTP.');
  }
  
  const otpKey = `otp:${email}`;
  const encryptedOtp = await this.redisService.get(otpKey);
  
  if (!encryptedOtp) {
    throw new BadRequestException('OTP expired');
  }
  
  const decryptedOtp = this.encryptionService.decrypt(JSON.parse(encryptedOtp));
  
  if (decryptedOtp !== otp) {
    await this.redisService.incr(attemptKey);
    await this.redisService.expire(attemptKey, 900); // 15 min window
    throw new BadRequestException('Invalid OTP');
  }
  
  // Success
  await this.redisService.del(attemptKey);
  await this.redisService.del(otpKey);
}
```

---

#### 3.3 - Complete RBAC Implementation
**File:** `gateway/src/common/guards/roles.guard.ts`, `gateway/src/common/decorators/roles.decorator.ts`
**Current Issue:** RolesGuard always returns true
**Action:**
- Implement proper role checking in guard
- Create @Roles() decorator
- Validate user.role matches endpoint requirement
- Support role hierarchies (Admin > Manager > User)

```typescript
// roles.decorator.ts
import { SetMetadata } from '@nestjs/common';

export const Roles = (...roles: UserRole[]) => SetMetadata('roles', roles);

// roles.guard.ts
import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import { Reflector } from '@nestjs/core';

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.get<UserRole[]>('roles', context.getHandler());
    if (!requiredRoles) {
      return true; // No roles required
    }

    const request = context.switchToHttp().getRequest();
    const user = request.user;

    if (!user || !user.role) {
      return false;
    }

    return requiredRoles.includes(user.role);
  }
}

// Usage in controller
@Post('admin/settings')
@Roles(UserRole.ADMIN)
async updateSettings(@Body() body: any) {
  // Only ADMIN can call
}
```

---

#### 3.4 - Add Login Audit Logging
**File:** `gateway/src/modules/auth/auth.service.ts`, create `audit.service.ts`
**Current Issue:** No logging of successful/failed login attempts
**Action:**
- Create AuditLog entity in database
- Log all auth events: login (success/fail), logout, password change, token refresh
- Track IP, user-agent, timestamp
- Alert on suspicious patterns (multiple IPs in short time, rapid failures)

```typescript
// audit.service.ts
export class AuditService {
  async logLoginAttempt(email: string, success: boolean, ipAddress: string, userAgent: string) {
    await this.prisma.auditLog.create({
      data: {
        event: 'LOGIN_ATTEMPT',
        email,
        success,
        ipAddress,
        userAgent,
        timestamp: new Date(),
      }
    });
    
    if (!success) {
      // Check for suspicious patterns
      const recentFailures = await this.prisma.auditLog.count({
        where: {
          email,
          success: false,
          timestamp: { gte: new Date(Date.now() - 3600000) } // 1 hour
        }
      });
      
      if (recentFailures > 10) {
        await this.alertService.sendSuspiciousActivityAlert(email);
      }
    }
  }
}
```

**Prisma schema:**
```prisma
model AuditLog {
  id        String   @id @default(cuid())
  event     String   // LOGIN_ATTEMPT, LOGOUT, PASSWORD_CHANGE, etc.
  email     String?
  userId    String?
  success   Boolean
  ipAddress String?
  userAgent String?
  details   String?  // JSON
  timestamp DateTime @default(now())
  
  @@index([email])
  @@index([userId])
  @@index([timestamp])
}
```

---

#### 3.5 - Implement Refresh Token Rotation
**File:** `gateway/src/modules/auth/auth.service.ts`
**Current Issue:** Refresh token reused; if compromised, works indefinitely
**Action:**
- On each token refresh, issue new refresh token
- Invalidate old refresh token
- Track refresh token rotation chains to detect replay attacks

```typescript
async refreshAccessToken(oldRefreshToken: string) {
  // Verify old refresh token is valid and in database
  const session = await this.prisma.session.findUnique({
    where: { refreshToken: oldRefreshToken }
  });
  
  if (!session || new Date() > session.expiresAt) {
    throw new UnauthorizedException('Invalid or expired refresh token');
  }
  
  // Generate new tokens
  const newAccessToken = this.generateAccessToken(session.userId);
  const newRefreshToken = this.generateRefreshToken(session.userId);
  
  // Invalidate old refresh token and create new session
  await this.prisma.session.update({
    where: { id: session.id },
    data: {
      refreshToken: newRefreshToken,
      expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
      rotatedAt: new Date(),
      rotationChain: session.rotationChain ? `${session.rotationChain},${oldRefreshToken}` : oldRefreshToken
    }
  });
  
  // Add old token to blacklist
  await this.tokenBlacklistService.addToken(oldRefreshToken, session.expiresAt);
  
  return { accessToken: newAccessToken, refreshToken: newRefreshToken };
}
```

---

#### 3.6 - Add Device Fingerprinting & Management
**File:** Create `device.service.ts`, `device.controller.ts`
**Current Issue:** Tokens can be used from any device; no way to detect compromise
**Action:**
- Create Device entity in database
- Hash device fingerprint (user-agent + IP + screen resolution, etc.)
- Store device fingerprint in JWT
- Alert user when new device logs in
- Allow user to revoke specific devices

```typescript
// device.service.ts
export class DeviceService {
  generateFingerprint(userAgent: string, ipAddress: string): string {
    const fingerprint = `${userAgent}|${ipAddress}`;
    return crypto.createHash('sha256').update(fingerprint).digest('hex');
  }

  async registerDevice(userId: string, fingerprint: string, ipAddress: string, userAgent: string) {
    return this.prisma.device.create({
      data: {
        userId,
        fingerprint,
        ipAddress,
        userAgent,
        lastUsedAt: new Date(),
        isActive: true
      }
    });
  }

  async validateDevice(userId: string, fingerprint: string) {
    const device = await this.prisma.device.findUnique({
      where: { fingerprint_userId: { fingerprint, userId } }
    });
    
    if (!device) {
      // New device - alert user
      await this.emailService.sendNewDeviceAlert(userId);
      return false;
    }
    
    // Update last used
    await this.prisma.device.update({
      where: { id: device.id },
      data: { lastUsedAt: new Date() }
    });
    
    return true;
  }
}

// Prisma schema
model Device {
  id          String   @id @default(cuid())
  userId      String
  fingerprint String
  ipAddress   String
  userAgent   String
  lastUsedAt  DateTime
  isActive    Boolean  @default(true)
  createdAt   DateTime @default(now())
  
  user        User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  
  @@unique([fingerprint, userId])
  @@index([userId])
}
```

---

### Phase 4: Operational & Extra Security (1 Month)

#### 4.1 - Add 2FA/MFA Support
**File:** Create `auth/mfa` module
**Dependencies:** Install `speakeasy` and `qrcode`
**Action:**
- Support Time-based OTP (TOTP) using TOTP apps
- Support SMS backup codes
- Support recovery codes
- Require 2FA for admin accounts

```typescript
// mfa.service.ts
import * as speakeasy from 'speakeasy';
import * as QRCode from 'qrcode';

export class MfaService {
  async setupTotp(userId: string, email: string) {
    const secret = speakeasy.generateSecret({
      name: `IntelliMaint (${email})`,
      issuer: 'IntelliMaint',
      length: 32
    });
    
    const qrCode = await QRCode.toDataURL(secret.otpauth_url);
    
    return {
      secret: secret.base32,
      qrCode,
      manualEntryKey: secret.base32
    };
  }

  verifyTotp(secret: string, token: string) {
    return speakeasy.totp.verify({
      secret,
      encoding: 'base32',
      token,
      window: 2 // Allow 30 seconds before/after
    });
  }
}
```

---

#### 4.2 - Session Management UI Endpoints
**File:** Create `devices/devices.controller.ts`
**Action:**
- `GET /devices` - List all active sessions/devices
- `DELETE /devices/:id` - Logout from specific device
- `POST /devices/:id/revoke` - Revoke access from device
- Show last login time, IP, location (via GeoIP), device name

```typescript
@Controller('devices')
@UseGuards(JwtAuthGuard)
export class DevicesController {
  @Get()
  getActiveSessions(@Request() req) {
    return this.deviceService.getDevicesByUser(req.user.userId);
  }

  @Delete(':id')
  revokeDevice(@Param('id') deviceId: string, @Request() req) {
    return this.deviceService.revokeDevice(deviceId, req.user.userId);
  }

  @Post(':id/logout')
  logoutFromDevice(@Param('id') deviceId: string, @Request() req) {
    return this.deviceService.logoutDevice(deviceId, req.user.userId);
  }
}
```

---

#### 4.3 - Email Verification on Account Changes
**File:** `gateway/src/modules/auth/auth.service.ts`
**Action:**
- When user changes email, send verification link to new email
- New email not active until verified
- Send notification to old email
- Implement email change token (single-use)

```typescript
async changeEmail(userId: string, newEmail: string) {
  // Generate single-use token
  const changeToken = crypto.randomBytes(32).toString('hex');
  const tokenExpiry = new Date(Date.now() + 24 * 60 * 60 * 1000); // 24h
  
  await this.prisma.user.update({
    where: { id: userId },
    data: {
      emailChangeToken: changeToken,
      emailChangePending: newEmail,
      emailChangeExpiry: tokenExpiry
    }
  });
  
  // Send verification email to new address
  await this.emailService.sendEmailChangeVerification(newEmail, changeToken);
  
  // Notify user of pending change
  const user = await this.prisma.user.findUnique({ where: { id: userId } });
  await this.emailService.sendEmailChangePending(user.email);
}
```

---

#### 4.4 - Remove Debug Console Logs
**File:** Multiple files
**Action:**
- Replace all `console.log()` with proper logging service
- Use Winston or Pino for structured logging
- Set log levels: debug, info, warn, error
- Only log non-sensitive data in production

```typescript
// logging.service.ts
import { Logger } from '@nestjs/common';

@Injectable()
export class LoggingService {
  private logger = new Logger();

  log(message: string, data?: any) {
    if (process.env.NODE_ENV === 'development') {
      this.logger.log(`${message}`, data);
    }
  }

  error(message: string, error?: any) {
    this.logger.error(message, error);
  }

  warn(message: string, data?: any) {
    this.logger.warn(`${message}`, data);
  }
}
```

**Remove all:**
```typescript
// ❌ Remove
console.log('login called successfully', body);

// ✅ Replace with
this.logger.debug('Login attempt', { email: body.email });
```

---

#### 4.5 - Implement Intrusion Detection System
**File:** Create `security/intrusion-detection.service.ts`
**Action:**
- Monitor for suspicious patterns (multiple IPs, rapid requests, etc.)
- Track IP reputation
- Implement IP whitelist/blacklist
- Alert admins on detected threats

```typescript
export class IntrusionDetectionService {
  async checkSuspiciousActivity(userId: string, ipAddress: string) {
    const recentLogins = await this.auditService.getLoginsByUser(userId, { hours: 1 });
    
    // Check multiple IPs in short time
    const uniqueIps = new Set(recentLogins.map(l => l.ipAddress));
    if (uniqueIps.size > 3) {
      await this.alertService.sendIntrusionAlert(userId, 'Multiple IPs detected');
      return true;
    }
    
    // Check IP reputation
    const ipReputation = await this.getIpReputation(ipAddress);
    if (ipReputation.isBlacklisted) {
      await this.alertService.sendIntrusionAlert(userId, 'Suspicious IP detected');
      return true;
    }
    
    return false;
  }
}
```

---

## Frontend Changes Required

### High Priority (Coordinate with Frontend Team)

1. **Token Refresh Handling**
   - Implement automatic token refresh before expiration
   - Create response interceptor to detect 401 and retry with new token
   - Handle token revocation (logout from another session means 401 is permanent)
   - Show "Session expired" message and redirect to login if refresh fails

```typescript
// Frontend interceptor
private setupInterceptors() {
  this.http.interceptors.response.use(
    response => response,
    error => {
      if (error.response?.status === 401) {
        // Try to refresh
        return this.authService.refreshToken()
          .then(newToken => {
            // Retry original request with new token
            return this.http(originalRequest);
          })
          .catch(() => {
            // Refresh failed - redirect to login
            this.router.navigate(['/login']);
            return Promise.reject(error);
          });
      }
      return Promise.reject(error);
    }
  );
}
```

2. **CSRF Token Submission**
   - Include `_csrf` in all POST/PUT/DELETE request bodies
   - OR include `X-CSRF-Token` header on all state-changing requests
   - Store CSRF token in memory (not localStorage) during session

```typescript
// Fetch CSRF token on app init
async initCsrfToken() {
  const response = await this.http.get('/auth/csrf-token');
  this.csrfToken = response.token;
}

// Include in requests
private setupInterceptors() {
  this.http.interceptors.request.use(request => {
    request.headers['X-CSRF-Token'] = this.csrfToken;
    return request;
  });
}
```

3. **OTP Input in Password Reset**
   - Add OTP field to forgot password form
   - Flow: 1) Enter email 2) Receive OTP 3) Enter OTP 4) Enter new password 5) Submit

```typescript
// password-reset.component.ts
forgotPasswordFlow = [
  { step: 1, title: 'Enter Email', field: 'email' },
  { step: 2, title: 'Enter OTP', field: 'otp' },
  { step: 3, title: 'New Password', field: 'newPassword' },
];

async resetPassword() {
  // POST to /auth/reset-password with { email, otp, newPassword }
}
```

4. **Device Management UI**
   - Show list of active sessions/devices
   - Display last login time, IP, device name
   - Allow logout from specific devices
   - Show new login alerts

```typescript
// devices/devices.component.ts
async loadDevices() {
  this.devices = await this.http.get('/devices');
  // Display with: device name, IP, last login, location
}

async logoutDevice(deviceId: string) {
  await this.http.post(`/devices/${deviceId}/logout`);
  this.loadDevices();
}
```

5. **Account Lockout Feedback**
   - Disable login form for 15 minutes when account locked
   - Show countdown timer
   - Offer "Unlock via email" button to send unlock code

```typescript
// login.component.ts
if (error.status === 429 && error.message.includes('locked')) {
  this.accountLocked = true;
  this.lockoutEndTime = new Date(Date.now() + 15 * 60 * 1000);
  this.startLockoutCountdown();
}
```

6. **Password Complexity Feedback**
   - Show real-time password strength meter
   - Display requirements checklist (length, uppercase, etc.)
   - Disable submit button until all requirements met

```typescript
// password-strength.component.ts
requirements = [
  { met: false, text: 'At least 12 characters' },
  { met: false, text: 'Contains uppercase letter' },
  { met: false, text: 'Contains lowercase letter' },
  { met: false, text: 'Contains number' },
  { met: false, text: 'Contains special character' },
];

checkPassword(password: string) {
  this.requirements[0].met = password.length >= 12;
  this.requirements[1].met = /[A-Z]/.test(password);
  // ... etc
}
```

7. **Secure Token Storage**
   - ✅ Access tokens: httpOnly cookie (set by backend)
   - ❌ DO NOT store access token in localStorage
   - ❌ DO NOT store refresh token in localStorage
   - Refresh tokens: Only in httpOnly cookie (backend handles rotation)
   - Session state: Can use sessionStorage or memory

8. **2FA Enrollment Flow (Future)**
   - GET /mfa/setup - Receive QR code and secret
   - Display QR code for scanning with authenticator app
   - Require user to enter 6-digit code to confirm
   - Show recovery codes and backup options

---

### Medium Priority

9. **Login Attempt Notifications**
   - Show IP and location of recent logins
   - Mark unrecognized devices
   - Provide "This wasn't me" quick action

10. **Email Change Verification**
    - When changing email, require verification of new email
    - Show verification status (pending/confirmed)
    - Send notification to old email

---

## Testing & Validation Checklist

### Unit Tests
- [ ] Rate limiting applies to correct endpoints
- [ ] Token revocation works (old tokens rejected after logout)
- [ ] OTP verification requires valid OTP
- [ ] Password reset requires OTP
- [ ] Password validation rejects weak passwords
- [ ] OAuth tokens are encrypted/decrypted correctly
- [ ] Device fingerprinting generates consistent hashes
- [ ] Account lockout triggers after 5 attempts
- [ ] Token rotation generates new tokens

### Integration Tests
- [ ] Complete registration → verification → login flow
- [ ] Token refresh generates new tokens
- [ ] Logout invalidates refresh token
- [ ] Password reset sends OTP → verifies → updates password
- [ ] Google OAuth login → stores encrypted tokens
- [ ] Automatic token refresh cron works correctly
- [ ] Multiple concurrent refreshes don't cause race conditions
- [ ] Audit logging captures all auth events

### Security Tests
- [ ] Brute force protection prevents credential stuffing
- [ ] CSRF tokens validated on state-changing requests
- [ ] Security headers present (HSTS, CSP, etc.)
- [ ] HTTPS redirect works
- [ ] Cookies have secure + httpOnly flags
- [ ] JWT signature validation prevents tampering
- [ ] Unverified token decoding removed
- [ ] OAuth tokens cannot be read in plaintext
- [ ] OTP expiration enforced
- [ ] Session blacklist prevents reuse of revoked tokens

### Penetration Testing
- [ ] Brute force attack on login (rate limiting)
- [ ] Brute force attack on OTP (attempt limiting)
- [ ] Token replay attacks (refresh token rotation)
- [ ] CSRF attack on form submission
- [ ] XSS attack trying to access httpOnly cookies
- [ ] SQL injection in auth queries (Prisma handles)
- [ ] JWT token modification (signature validation)
- [ ] Account enumeration via forgot password

### Accessibility & User Experience
- [ ] Error messages are clear and helpful
- [ ] Password strength meter guides users
- [ ] Account lockout message is understandable
- [ ] Device management UI is intuitive
- [ ] OTP verification process is smooth
- [ ] 2FA enrollment process is clear

---

## Environment Variables Needed

```bash
# Required (Critical)
JWT_SECRET=<32+ character random string>
ENCRYPTION_KEY=<64 hex characters, generated by: node -e "console.log(require('crypto').randomBytes(32).toString('hex'))">

# Required (Existing)
DATABASE_URL=<your-database-url>
GOOGLE_CLIENT_ID=<google-oauth-client-id>
GOOGLE_CLIENT_SECRET=<google-oauth-secret>
FRONTEND_URL=<frontend-domain>

# Optional but Recommended
NODE_ENV=production|development|staging
LOG_LEVEL=debug|info|warn|error
RATE_LIMIT_LOGIN=5  # attempts
RATE_LIMIT_WINDOW=900000  # 15 minutes in ms
EMAIL_SERVICE=<provider>  # sendgrid, mailgun, etc.
```

---

## Success Criteria

### Phase 1 Completion
- All 5 critical vulnerabilities fixed and tested
- No unencrypted sensitive data in database
- Rate limiting active on auth endpoints
- Token revocation working end-to-end

### Phase 2 Completion
- Security headers present in all responses
- CSRF protection implemented and tested
- HTTPS redirect active
- Account lockout functional
- No JavaScript access to sensitive cookies

### Phase 3 Completion
- Device fingerprinting working
- Token rotation implemented
- RBAC fully functional
- Audit logging comprehensive
- OTP fully encrypted and limited

### Phase 4 Completion
- 2FA optional/required for admins
- Session management UI live
- All debug logs removed
- Intrusion detection monitoring
- Email verification on changes working

---

## Rollout Strategy

### Week 1: Phase 1
- Deploy with feature flags (disable new features initially)
- Test on staging environment
- Enable rate limiting for testing users
- Monitor for issues
- Deploy to production with gradual rollout (5% users first)

### Week 2: Phase 2
- Security headers can be deployed immediately (non-breaking)
- CSRF tokens require frontend coordination
- Plan frontend deployment alongside backend

### Week 3-4: Phase 3
- Device fingerprinting is optional (non-breaking)
- Token rotation requires frontend update
- RBAC enforcement needs careful testing

### Week 5: Phase 4
- Optional features (2FA, session UI)
- Can be deployed incrementally without blocking other features

---

## Rollback Plan

Each phase can be rolled back independently:
1. **Phase 1**: Disable rate limiting, restore old token handling (keep revocation)
2. **Phase 2**: Disable CSRF validation, remove HTTPS redirect
3. **Phase 3**: Disable device checks, revert to old token refresh
4. **Phase 4**: Disable new features (they're optional)

---

## Documentation for Users

### For End Users
- "How to enable 2FA"
- "How to manage devices and sessions"
- "What to do if your account was compromised"
- "Password requirements"

### For Administrators
- "How to monitor suspicious activity"
- "How to investigate audit logs"
- "How to disable a user account"

### For Frontend Developers
- "Token refresh implementation guide"
- "CSRF token usage"
- "Error handling for 401 responses"
- "Device management UI integration"

---
