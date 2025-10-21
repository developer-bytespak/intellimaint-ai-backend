import { Controller, Post, Get, Body, Param } from '@nestjs/common';
import { BillingService } from '../services/billing.service';

@Controller('billing')
export class BillingController {
  constructor(private billingService: BillingService) {}

  @Post('subscribe')
  async createSubscription(@Body() subscriptionDto: any) {
    return this.billingService.createSubscription(subscriptionDto);
  }

  @Get('invoices/:userId')
  async getInvoices(@Param('userId') userId: string) {
    return this.billingService.getInvoices(userId);
  }
}

