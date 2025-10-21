import { IsBoolean, IsString, IsOptional } from 'class-validator';

export class SettingsDto {
  @IsBoolean()
  @IsOptional()
  notifications?: boolean;

  @IsString()
  @IsOptional()
  theme?: string;
}

