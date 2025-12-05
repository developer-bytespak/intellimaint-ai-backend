import { IsString, IsOptional, IsArray } from 'class-validator';

export class CreateMessageDto {
  @IsString()
  content: string;

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  images?: string[];
}

