import { IsString } from 'class-validator';

export class SubscriptionDto {
  @IsString()
  priceId!: string;

  @IsString()
  userId!: string;
}

