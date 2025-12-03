import { IsBoolean, IsString, IsOptional } from 'class-validator';

export class SettingsDto {
  @IsBoolean()
  @IsOptional()
  emailNotifications?: boolean;

  @IsString()
  @IsOptional()
  theme?: string;
}

