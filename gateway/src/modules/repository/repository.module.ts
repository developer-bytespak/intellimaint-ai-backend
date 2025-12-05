import { Module } from '@nestjs/common';
import { RepositoryController } from './controllers/repository.controller';
import { RepositoryService } from './services/repository.service';
import { PrismaService } from 'prisma/prisma.service';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [AuthModule],
  controllers: [RepositoryController],
  providers: [RepositoryService, PrismaService],
  exports: [RepositoryService],
})
export class RepositoryModule {}

