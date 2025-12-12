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
  // Normalize FRONTEND_URL env var (split, trim, strip trailing slashes)
  const rawOrigins = process.env.FRONTEND_URL?.split(',') || [
    'http://localhost:3001',
  ];
  const allowedOrigins = rawOrigins.map((o) =>
    String(o).trim().replace(/\/+$/, ''),
  );
  console.log('CORS allowed origins:', allowedOrigins);
  
  // Enhanced CORS configuration for authentication with credentials
  app.enableCors({
    origin: allowedOrigins,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Cookie'],
    exposedHeaders: ['Content-Type', 'X-Total-Count', 'Set-Cookie'],
    maxAge: 3600,
  });

  app.use(cookieParser.default());

  await app.listen(appConfig.port);
  console.log(`Application is running on: ${await app.getUrl()}`);
}

bootstrap();
