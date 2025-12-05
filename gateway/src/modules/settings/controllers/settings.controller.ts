import { Controller, Get, Put, Body, Req, UseGuards, Res } from '@nestjs/common';
import { SettingsService } from '../services/settings.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';
import { SettingsDto } from '../dto/settings.dto';
import { nestResponse, nestError } from 'src/common/helpers/responseHelpers';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import type { Response } from 'express';

@Controller('user')
@UseGuards(JwtAuthGuard)
export class SettingsController {
  constructor(private settingsService: SettingsService) {}

  @Get('settings')
  async getSettings(@Req() req: any, @Res({ passthrough: true }) res: Response) {
    try {
      const userId = req.user.id;
      const settings = await this.settingsService.getSettings(userId);
      return nestResponse(200, 'Settings retrieved successfully', settings)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 404) {
        return nestError(404, err.message || 'Not found')(res);
      }
      return nestError(500, 'Failed to retrieve settings', err.message || 'Internal server error')(res);
    }
  }

  @Put('settings')
  async updateSettings(
    @Req() req: any,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const settingsDto = plainToInstance(SettingsDto, body);
      const errors = await validate(settingsDto);
      
      if (errors.length > 0) {
        const messages = errors.map(err => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const settings = await this.settingsService.updateSettings(userId, settingsDto);
      return nestResponse(200, 'Settings updated successfully', settings)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 404) {
        return nestError(404, err.message || 'Not found')(res);
      }
      return nestError(500, 'Failed to update settings', err.message || 'Internal server error')(res);
    }
  }
}
