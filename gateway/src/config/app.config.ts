export const appConfig = {
  port: process.env.PORT || 8000,
  environment: process.env.NODE_ENV || 'development',
  apiPrefix: '/api/v1',
  jwtSecret: process.env.JWT_SECRET,
  redisUrl: process.env.REDIS_URL,
  portalEmail: process.env.PORTAL_EMAIL,
  portalPassword: process.env.PORTAL_PASSWORD,
};

