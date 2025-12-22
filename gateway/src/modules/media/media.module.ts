import { Module } from '@nestjs/common';
import { MediaController } from './controllers/media.controller';
import { MediaService } from './services/media.service';
import { PrismaService } from 'prisma/prisma.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Module({
  controllers: [MediaController],
  providers: [MediaService, PrismaService, JwtAuthGuard],
  exports: [MediaService],
})
export class MediaModule {}

