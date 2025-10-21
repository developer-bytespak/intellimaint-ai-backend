import { Controller, Post, Headers, RawBodyRequest, Req } from '@nestjs/common';
import { Request } from 'express';

@Controller('webhooks')
export class StripeWebhookController {
  @Post('stripe')
  async handleStripeWebhook(
    @Headers('stripe-signature') signature: string,
    @Req() request: RawBodyRequest<Request>,
  ) {
    // Handle Stripe webhook events
    return { received: true };
  }
}

