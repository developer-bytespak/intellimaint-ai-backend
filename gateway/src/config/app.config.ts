export const appConfig = {
  port: process.env.PORT || 8000,
  environment: process.env.NODE_ENV || 'development',
  apiPrefix: '/api/v1',
  jwtSecret: process.env.JWT_SECRET,
  redisUrl: process.env.REDIS_URL || 'redis://127.0.0.1:6379',
  redisPort: process.env.REDIS_PORT || 6379,
  redisPassword: process.env.REDIS_PASSWORD || '',
  portalEmail: process.env.PORTAL_EMAIL,
  portalPassword: process.env.PORTAL_PASSWORD,
  token: process.env.BLOB_READ_WRITE_TOKEN,
  aiServicesUrl: process.env.AI_SERVICES_URL || 'http://localhost:8000',
  gemini: {
    apiKey: process.env.GEMINI_API_KEY,
    modelName: process.env.GEMINI_MODEL_NAME || 'gemini-2.5-flash',
  },
};
