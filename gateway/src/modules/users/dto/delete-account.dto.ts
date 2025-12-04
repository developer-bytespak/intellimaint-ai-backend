import { IsString, IsOptional } from 'class-validator';

export class DeleteAccountDto {
  @IsString()
  @IsOptional()
  password?: string;

  @IsString()
  @IsOptional()
  otp?: string;
}

