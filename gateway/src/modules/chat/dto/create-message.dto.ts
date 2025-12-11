import { IsString, IsOptional, IsArray, ValidateIf, IsNotEmpty } from 'class-validator';

export class CreateMessageDto {
  @IsOptional()
  @IsString()
  content?: string;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  images?: string[];

  // Custom validation: at least one of content or images must be provided
  // This is handled in the service layer with explicit check
}

