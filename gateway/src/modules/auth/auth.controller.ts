/* eslint-disable @typescript-eslint/no-unsafe-assignment,
                  @typescript-eslint/no-unsafe-member-access,
                  @typescript-eslint/no-unsafe-call,
                  @typescript-eslint/no-unsafe-return,
                  @typescript-eslint/no-unsafe-argument */

import {
  Controller,
  Get,
  UseGuards,
  Req,
  Post,
  Res,
  Next,
  Body,
} from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { AuthService } from './auth.service';
import type { Response, Request } from 'express';
import { JwtAuthGuard } from './jwt-auth.guard';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';
import { RegisterDto } from './dto/login.dto';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  // Google Login
  @Get('google')
  googleAuth(@Req() req: Request, @Res() res: Response) {
    const googleToken = req.cookies?.google_accessToken;
    const localToken = req.cookies?.local_accessToken;
    const role = (req as any).query.role as string;
    const company = (req as any).query.company as string;

    // If user already has a valid token, redirect to chat
    if (googleToken || localToken) {
      try {
        return res.redirect(`${process.env.FRONTEND_URL}/chat`);
      } catch (e) {
        // Clear cookies if there's an error
        res.clearCookie('google_accessToken', {
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
          sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
          path: '/',
        });
        res.clearCookie('local_accessToken', {
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
          sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
          path: '/',
        });
      }
    }
    const passportInstance =
      (req as any)._passport?.instance || require('passport');

    return passportInstance.authenticate('google', {
      scope: ['email', 'profile'],
      prompt: 'consent',
      accessType: 'offline',
      state: JSON.stringify({ role, company }),
    } as any)(req, res);
  }

  @Get('google/redirect')
  @UseGuards(AuthGuard('google'))
  async googleRedirect(@Req() req, @Res({ passthrough: true }) res: Response) {
    try {
      let { role, company } = JSON.parse(req.query.state as string);
      // console.log("role", role);
      // console.log("company", company);

      const email = req.user.email;

      if (role === '') {
        const existingUser = await this.authService.checkUserEmail(email);
        if (!existingUser) {
          return res.redirect(
            `${process.env.FRONTEND_URL}/callback?error=No user found with this email`,
          );
        }

        role = existingUser.role;
      }
      // console.log('role', role);

      if (email.endsWith('.com')) {
        if (role !== 'civilian') {
          return res.redirect(
            `${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`,
          );
        }
      } else if (email.endsWith('.edu')) {
        if (role !== 'student') {
          return res.redirect(
            `${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`,
          );
        }
      } else if (email.endsWith('.mil')) {
        if (role !== 'military') {
          return res.redirect(
            `${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`,
          );
        }
      } else {
        return res.redirect(
          `${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`,
        );
      }

      const authResult = await this.authService.googleLogin(
        req.user,
        role,
        company,
        res as any,
      );
      const { accessToken, refreshToken, isNewUser, user } = authResult as {
        accessToken: string;
        refreshToken: string;
        isNewUser: boolean;
        user: any;
      };

      // Set Google access token cookie with proper CORS settings
      res.cookie('google_accessToken', accessToken, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
        path: '/',
        maxAge: 1 * 60 * 60 * 1000, // 1 hour
      });

      // Set Google refresh token cookie
      res.cookie('google_refreshToken', refreshToken, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
        path: '/',
        maxAge: 14 * 24 * 60 * 60 * 1000, // 14 days
      });

      // if (!isNewUser) {
      //   return nestResponse(201, 'User created successfully', user)(res);
      // }
      // return nestResponse(200, 'Login successful', user)(res);
      return res.redirect(`${process.env.FRONTEND_URL}/chat`);
    } catch (error) {
      if (error.status === 400) {
        return res.redirect(
          `${process.env.FRONTEND_URL}/callback?error=${encodeURIComponent(error.message || 'Account has been deleted')}`,
        );
      }
      return res.redirect(
        `${process.env.FRONTEND_URL}/callback?error=${encodeURIComponent('Authentication failed')}`,
      );
    }
  }
  @Post('refresh')
  async refreshAccessToken(@Req() req, @Res({ passthrough: true }) res: Response) {
    // Validate refreshToken and generate new access token
    await this.authService.refreshAccessToken(req, res);
  }

  @UseGuards(JwtAuthGuard)
  @Get('profile')
  getProfile(@Req() req: Request) {
    return {
      message: 'User authenticated!',
      user: req.user,
    };
  }

  // Logout
  @UseGuards(JwtAuthGuard)
  @Get('logout')
  async logout(@Req() req: Request, @Res({ passthrough: true }) res: Response) {
    console.log('logout called successfully');
    // Clear all auth cookie
    const userId = (req as any).user?.id;
    if (!userId) {
      nestError(400, 'User not found')(res);
      return;
    }
    // await redisDeleteKey(`user_active:${userId}`);

    res.clearCookie('local_accessToken', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
      sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
      path: '/',
    });
    res.clearCookie('google_accessToken', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
      sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
      path: '/',
    });
    res.clearCookie('local_refreshToken', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
      sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
      path: '/',
    });
    res.clearCookie('google_refreshToken', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
      sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
      path: '/',
    });
    res.redirect(`${process.env.FRONTEND_URL}/login`);
  }

  // Register
  @Post('register')
  async register(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    console.log('register called successfully', body);
    const email = body.email;
    const role = body.role;
    if (email.endsWith('.com')) {
      if (role !== 'civilian') {
        nestError(400, 'your email is not fit in your role')(res);
        return;
      }
    } else if (email.endsWith('.edu')) {
      if (role !== 'student') {
        nestError(400, 'your email is not fit in your role')(res);
        return;
      }
    } else if (email.endsWith('.mil')) {
      if (role !== 'military') {
        nestError(400, 'your email is not fit in your role')(res);
        return;
      }
    } else {
      nestError(400, 'your email is not fit in your role')(res);
      return;
    }

    // Map custom input to RegisterDto
    const registerDto = plainToInstance(RegisterDto, {
      email: body.email,
      password: body.password,
      confirmPassword: body.confirmPassword,
      role: body.role,
      firstName: body.firstName,
      lastName: body.lastName,
      company: body.company,
    });

    // Validate the DTO manually
    const errors = await validate(registerDto);
    if (errors.length > 0) {
      // Convert class-validator errors to readable messages
      const messages = errors
        .map((err) => Object.values(err.constraints || {}))
        .flat();
      nestError(400, 'Validation failed', messages)(res);
      return;
    }

    if (registerDto.password !== registerDto.confirmPassword) {
      nestError(400, 'Password and confirm password do not match')(res);
      return;
    }

    await this.authService.register(registerDto, res as any);
  }

  // Verify OTP
  @Post('verify-otp')
  async verifyOtp(
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    await this.authService.verifyOtp(body, res as any);
  }

  // Resend OTP
  @Post('resend-otp')
  async resendOtp(
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    await this.authService.resendOtp(body, res as any);
  }

  // Login
  @Post('login')
  async login(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    console.log('login called successfully', body);
    await this.authService.login(body, res as any);
  }

  // Forgot Password
  @Post('forgot-password')
  async forgotPassword(
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    await this.authService.forgotPassword(body, res as any);
  }

  // Reset password
  @Post('reset-password')
  async resetPassword(
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    await this.authService.resetPassword(body, res as any);
  }
}
