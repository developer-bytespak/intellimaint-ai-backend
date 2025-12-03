import { Module } from '@nestjs/common';
import { SettingsService } from './services/settings.service';
import { PrismaService } from 'prisma/prisma.service';

@Module({
  providers: [SettingsService, PrismaService],
  exports: [SettingsService],
})
export class SettingsModule {}
