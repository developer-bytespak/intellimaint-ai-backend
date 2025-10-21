import { Module } from '@nestjs/common';
import { AuthModule } from './modules/auth/auth.module';
import { UsersModule } from './modules/users/users.module';
import { ChatModule } from './modules/chat/chat.module';
import { MediaModule } from './modules/media/media.module';
import { BillingModule } from './modules/billing/billing.module';
import { RagModule } from './modules/rag/rag.module';
import { SettingsModule } from './modules/settings/settings.module';
import { AuditModule } from './modules/audit/audit.module';
import { AdminModule } from './modules/admin/admin.module';
import { HealthModule } from './modules/health/health.module';

@Module({
  imports: [
    AuthModule,
    UsersModule,
    ChatModule,
    MediaModule,
    BillingModule,
    RagModule,
    SettingsModule,
    AuditModule,
    AdminModule,
    HealthModule,
  ],
})
export class AppModule {}

