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

  // Get allowed origins from environment variable
  const allowedOriginsStr =
    process.env.FRONTEND_URL || 'http://localhost:3001,http://localhost:3000';
  const allowedOrigins = allowedOriginsStr
    .split(',')
    .map((origin) => origin.trim());

  // Add production frontends if not already in the list
  const productionFrontends = [
    'https://intellimaint-ai.onrender.com',
    'https://intellimaint-ai.vercel.app',
  ];
  productionFrontends.forEach((frontend) => {
    if (!allowedOrigins.includes(frontend)) {
      allowedOrigins.push(frontend);
    }
  });

  console.log('CORS enabled for origins:', allowedOrigins);

  app.enableCors({
    origin: allowedOrigins,
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
  });

  app.use(cookieParser.default());

  await app.listen(appConfig.port);
  console.log(`Application is running on: ${await app.getUrl()}`);
}

bootstrap();
