import { IsString } from 'class-validator';

export class MessageDto {
  @IsString()
  content!: string;

  @IsString()
  sessionId!: string;
}

