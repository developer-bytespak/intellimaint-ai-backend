import { Module } from '@nestjs/common';
import { BillingController } from './controllers/billing.controller';
import { BillingService } from './services/billing.service';
import { StripeWebhookController } from './webhook/stripe.webhook';

@Module({
  controllers: [BillingController, StripeWebhookController],
  providers: [BillingService],
  exports: [BillingService],
})
export class BillingModule {}

