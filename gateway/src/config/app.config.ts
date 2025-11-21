export const appConfig = {
  port: process.env.PORT || 8000,
  environment: process.env.NODE_ENV || 'development',
  apiPrefix: '/api/v1',
  jwtSecret: process.env.JWT_SECRET,
  redisUrl: process.env.REDIS_URL || "redis://127.0.0.1:6379",
  redisPort: process.env.REDIS_PORT || 6379,
  redisPassword: process.env.REDIS_PASSWORD || "",
  portalEmail: process.env.PORTAL_EMAIL,
  portalPassword: process.env.PORTAL_PASSWORD,
};

