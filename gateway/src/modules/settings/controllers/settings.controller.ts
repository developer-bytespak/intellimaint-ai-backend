import { Controller, Get, Put, Param, Body } from '@nestjs/common';
import { SettingsService } from '../services/settings.service';

@Controller('settings')
export class SettingsController {
  constructor(private settingsService: SettingsService) {}

  @Get(':userId')
  async getSettings(@Param('userId') userId: string) {
    return this.settingsService.getSettings(userId);
  }

  @Put(':userId')
  async updateSettings(@Param('userId') userId: string, @Body() settingsDto: any) {
    return this.settingsService.updateSettings(userId, settingsDto);
  }
}

