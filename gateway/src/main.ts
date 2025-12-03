import 'dotenv/config';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe } from '@nestjs/common';
import { appConfig } from './config/app.config';
import * as cookieParser from 'cookie-parser';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  
  app.useGlobalPipes(new ValidationPipe());
  app.setGlobalPrefix(appConfig.apiPrefix);
  app.enableCors(
    {
      origin: ["http://localhost:3001", "http://localhost:5173"],
      credentials: true,
    }
  );
  

  app.use(cookieParser.default());


 
  await app.listen(appConfig.port);
  console.log(`Application is running on: ${await app.getUrl()}`);

}

bootstrap();

