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
  app.enableCors(
    {
      origin: process.env.FRONTEND_URL?.split(',') || ["http://localhost:3001"],
      credentials: true,
    }
  );
  

  app.use(cookieParser.default());


 
  await app.listen(appConfig.port);
  console.log(`Application is running on: ${await app.getUrl()}`);

}

bootstrap();

