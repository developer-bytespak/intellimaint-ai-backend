import { Controller, Get, Put, Post, Delete, Body, Req, UseGuards, Res } from '@nestjs/common';
import { UsersService } from '../services/users.service';
import { SettingsService } from '../../settings/services/settings.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';
import { UpdateProfileDto } from '../dto/update-profile.dto';
import { ChangePasswordDto } from '../dto/change-password.dto';
import { DeleteAccountDto } from '../dto/delete-account.dto';
import { SettingsDto } from '../../settings/dto/settings.dto';
import { nestResponse, nestError } from 'src/common/helpers/responseHelpers';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import { redisDeleteKey } from 'src/common/lib/redis';
import type { Response } from 'express';

@Controller('user')
@UseGuards(JwtAuthGuard)
export class UsersController {
  constructor(
    private usersService: UsersService,
    private settingsService: SettingsService,
  ) {}

  @Get('profile')
  async getProfile(@Req() req: any, @Res({ passthrough: true }) res: Response) {
    try {
      const userId = req.user.id;
      const user = await this.usersService.getProfile(userId);
      return nestResponse(200, 'Profile retrieved successfully', user)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 404) {
        return nestError(404, err.message || 'Not found')(res);
      }
      return nestError(500, 'Failed to retrieve profile', err.message || 'Internal server error')(res);
    }
  }

  @Put('profile')
  async updateProfile(
    @Req() req: any,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const updateDto = plainToInstance(UpdateProfileDto, body);
      const errors = await validate(updateDto);
      
      if (errors.length > 0) {
        const messages = errors.map(err => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const updatedUser = await this.usersService.updateProfile(userId, updateDto);
      return nestResponse(200, 'Profile updated successfully', updatedUser)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 400 || err.status === 404) {
        return nestError(err.status, err.message || 'Bad request')(res);
      }
      return nestError(500, 'Failed to update profile', err.message || 'Internal server error')(res);
    }
  }

  @Put('password')
  async changePassword(
    @Req() req: any,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const changePasswordDto = plainToInstance(ChangePasswordDto, body);
      const errors = await validate(changePasswordDto);
      
      if (errors.length > 0) {
        const messages = errors.map(err => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const result = await this.usersService.changePassword(userId, changePasswordDto);
      return nestResponse(200, result.message, null)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 400 || err.status === 404) {
        return nestError(err.status, err.message || 'Bad request')(res);
      }
      return nestError(500, 'Failed to change password', err.message || 'Internal server error')(res);
    }
  }

  @Post('account/delete-otp')
  async sendDeleteAccountOtp(
    @Req() req: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const result = await this.usersService.sendDeleteAccountOtp(userId);
      return nestResponse(200, result.message, null)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 400 || err.status === 404) {
        return nestError(err.status, err.message || 'Bad request')(res);
      }
      return nestError(500, 'Failed to send OTP', err.message || 'Internal server error')(res);
    }
  }

  @Delete('account')
  async deleteAccount(
    @Req() req: any,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const deleteDto = plainToInstance(DeleteAccountDto, body);
      const errors = await validate(deleteDto);
      
      if (errors.length > 0) {
        const messages = errors.map(err => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const result = await this.usersService.deleteAccount(userId, deleteDto);
      
      // Clear authentication cookies
      res.clearCookie('local_access', { httpOnly: true, sameSite: 'lax', path: '/' });
      res.clearCookie('google_access', { httpOnly: true, sameSite: 'lax', path: '/' });
      res.clearCookie('refresh_token', { httpOnly: true, sameSite: 'lax', path: '/' });
      res.clearCookie('google_user_email', { httpOnly: false, sameSite: 'lax', path: '/' });
      
      // Clear Redis cache
      await redisDeleteKey(`user_active:${userId}`);
      
      return nestResponse(200, result.message, null)(res);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err.status === 400 || err.status === 404) {
        return nestError(err.status, err.message || 'Bad request')(res);
      }
      return nestError(500, 'Failed to delete account', err.message || 'Internal server error')(res);
    }
  }

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
