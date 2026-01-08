export const appConfig = {
  port: process.env.PORT || 8000,
  environment: process.env.NODE_ENV || 'development',
  apiPrefix: '/api/v1',
  jwtSecret: process.env.JWT_SECRET,
  redisUrl: process.env.REDIS_URL || 'redis://127.0.0.1:6379',
  redisPort: process.env.REDIS_PORT || 6379,
  redisPassword: process.env.REDIS_PASSWORD || '',
  sendgrid: {
    apiKey: process.env.SENDGRID_API_KEY,
    fromEmail: process.env.SENDGRID_FROM_EMAIL,
  },
  token: process.env.BLOB_READ_WRITE_TOKEN,
  aiServicesUrl: process.env.AI_SERVICES_URL || 'http://localhost:8000',
  openai: {
    apiKey: process.env.OPENAI_API_KEY || '',
    modelName: process.env.OPENAI_MODEL_NAME || 'gpt-4o',
  },
};
