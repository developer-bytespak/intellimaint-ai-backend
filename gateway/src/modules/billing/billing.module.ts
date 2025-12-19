import { Module } from '@nestjs/common';
import { BillingController } from './controllers/billing.controller';
import { BillingService } from './services/billing.service';
import { StripeWebhookController } from './webhook/stripe.webhook';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { PrismaService } from 'prisma/prisma.service';

@Module({
  controllers: [BillingController, StripeWebhookController],
  providers: [BillingService, PrismaService, JwtAuthGuard],
  exports: [BillingService],
})
export class BillingModule {}

