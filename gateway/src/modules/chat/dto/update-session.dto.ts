import { IsString, IsOptional, IsArray, IsEnum } from 'class-validator';
import { ChatSessionStatus } from '@prisma/client';

export class UpdateSessionDto {
  @IsString()
  @IsOptional()
  title?: string;

  @IsEnum(ChatSessionStatus)
  @IsOptional()
  status?: ChatSessionStatus;

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  equipmentContext?: string[];
}

