import 'dotenv/config';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe } from '@nestjs/common';
import { appConfig } from './config/app.config';
import * as cookieParser from 'cookie-parser';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,
      transformOptions: {
        enableImplicitConversion: true,
      },
    }),
  );

  app.setGlobalPrefix(appConfig.apiPrefix);

  /**
   * CORS CONFIGURATION
   * - Works on Render
   * - Supports cookies
   * - Allows multiple frontends
   * - Strict in production, relaxed in development
   */

  const allowedOriginsStr =
    process.env.FRONTEND_URL ||
    'http://localhost:3001,http://localhost:3000';

  const allowedOrigins = allowedOriginsStr
    .split(',')
    .map((origin) => origin.trim());

  // Ensure Vercel frontend is always allowed
  const productionFrontend = 'https://intellimaint-ai.vercel.app';
  if (!allowedOrigins.includes(productionFrontend)) {
    allowedOrigins.push(productionFrontend);
  }

  console.log('Allowed CORS origins:', allowedOrigins);

  app.enableCors({
    origin: (origin: string | undefined, callback) => {
      // Allow server-to-server, Postman, mobile apps
      if (!origin) {
        return callback(null, true);
      }

      if (allowedOrigins.includes(origin)) {
        return callback(null, true);
      }

      if (process.env.NODE_ENV === 'development') {
        return callback(null, true);
      }

      console.warn('CORS blocked origin:', origin);
      callback(new Error('Not allowed by CORS'));
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'Cookie',
      'Accept',
      'Origin',
      'X-Requested-With',
    ],
    exposedHeaders: ['Set-Cookie'],
    optionsSuccessStatus: 204,
  });

  app.use(cookieParser.default());

  await app.listen(appConfig.port);
  console.log(`Application is running on: ${await app.getUrl()}`);
}

bootstrap();
