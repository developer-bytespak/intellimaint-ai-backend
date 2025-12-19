/**
 * Cookie Configuration Helper for Cross-Domain Requests
 * 
 * When frontend (Vercel) and backend (Render) are on different domains,
 * we need sameSite: 'none' with secure: true for cookies to work.
 * 
 * For localhost development, sameSite: 'lax' works fine.
 */

export interface CookieOptions {
  httpOnly: boolean;
  secure: boolean;
  sameSite: 'strict' | 'lax' | 'none';
  path: string;
  maxAge?: number;
  domain?: string;
}

/**
 * Determines if we're in a cross-domain (production) environment
 */
export const isCrossDomain = (): boolean => {
  return process.env.NODE_ENV === 'production' || process.env.CROSS_DOMAIN === 'true';
};

/**
 * Get cookie configuration based on environment
 * For cross-domain: sameSite='none', secure=true
 * For same-domain (localhost): sameSite='lax', secure based on NODE_ENV
 */
export const getCookieConfig = (maxAge?: number): CookieOptions => {
  const crossDomain = isCrossDomain();
  
  return {
    httpOnly: true,
    secure: crossDomain ? true : process.env.NODE_ENV === 'production',
    sameSite: crossDomain ? 'none' : 'lax',
    path: '/',
    ...(maxAge && { maxAge }),
  };
};

/**
 * Cookie configurations for different token types
 */
export const cookieConfigs = {
  accessToken: (): CookieOptions => getCookieConfig(60 * 60 * 1000), // 1 hour
  refreshToken: (): CookieOptions => getCookieConfig(14 * 24 * 60 * 60 * 1000), // 14 days
  clearCookie: (): Omit<CookieOptions, 'maxAge'> => {
    const crossDomain = isCrossDomain();
    return {
      httpOnly: true,
      secure: crossDomain ? true : process.env.NODE_ENV === 'production',
      sameSite: crossDomain ? 'none' : 'lax',
      path: '/',
    };
  },
};

/**
 * Helper to set access token cookie
 */
export const setAccessTokenCookie = (res: any, name: string, token: string): void => {
  res.cookie(name, token, cookieConfigs.accessToken());
};

/**
 * Helper to set refresh token cookie
 */
export const setRefreshTokenCookie = (res: any, name: string, token: string): void => {
  res.cookie(name, token, cookieConfigs.refreshToken());
};

/**
 * Helper to clear a cookie with proper cross-domain config
 */
export const clearAuthCookie = (res: any, name: string): void => {
  res.clearCookie(name, cookieConfigs.clearCookie());
};

/**
 * Clear all auth cookies
 */
export const clearAllAuthCookies = (res: any): void => {
  const config = cookieConfigs.clearCookie();
  res.clearCookie('local_accessToken', config);
  res.clearCookie('google_accessToken', config);
  res.clearCookie('local_refreshToken', config);
  res.clearCookie('google_refreshToken', config);
};
