import 'dotenv/config';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe } from '@nestjs/common';
import { appConfig } from './config/app.config';
import * as cookieParser from 'cookie-parser';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  
  app.useGlobalPipes(new ValidationPipe({
    transform: true,
    transformOptions: {
      enableImplicitConversion: true,
    },
  }));
  app.setGlobalPrefix(appConfig.apiPrefix);
  
  // CORS configuration - support multiple origins
  const allowedOrigins = process.env.FRONTEND_URL 
    ? process.env.FRONTEND_URL.split(',').map(url => url.trim())
    : ["http://localhost:3001"];
  
  // Add Vercel domain if it's not already included
  const vercelDomain = "https://intellimaint-ai.vercel.app";
  if (!allowedOrigins.includes(vercelDomain)) {
    allowedOrigins.push(vercelDomain);
  }
  
  console.log('Allowed CORS origins:', allowedOrigins);
  
  app.enableCors({
    origin: (origin: string | undefined, callback: (err: Error | null, allow?: boolean) => void) => {
      // Allow requests with no origin (mobile apps, Postman, etc.)
      if (!origin) {
        return callback(null, true);
      }
      
      // Check if origin is in allowed list - EXACT match required (not *)
      if (allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        // In development, allow all origins for easier testing
        if (process.env.NODE_ENV === 'development') {
          callback(null, true);
        } else {
          // In production, be strict but log the rejected origin
          console.warn('CORS blocked origin:', origin);
          console.warn('Allowed origins:', allowedOrigins);
          callback(new Error('Not allowed by CORS'));
        }
      }
    },
    credentials: true, // Required for cookies
    methods: ['GET', 'HEAD', 'PUT', 'PATCH', 'POST', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Accept'],
    exposedHeaders: ['Set-Cookie'],
    preflightContinue: false,
    optionsSuccessStatus: 204,
  });
  

  app.use(cookieParser.default());


 
  await app.listen(appConfig.port);
  console.log(`Application is running on: ${await app.getUrl()}`);

}

bootstrap();

