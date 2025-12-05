import { IsString, IsOptional, IsObject } from 'class-validator';

export class AuditLogDto {
  @IsString()
  userId!: string;

  @IsString()
  action!: string;

  @IsObject()
  @IsOptional()
  metadata?: any;
}

