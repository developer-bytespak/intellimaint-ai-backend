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
import { cookieConfigs, clearAllAuthCookies } from 'src/common/helpers/cookieConfig';

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
        res.clearCookie('google_accessToken', cookieConfigs.clearCookie());
        res.clearCookie('local_accessToken', cookieConfigs.clearCookie());
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
  async googleRedirect(@Req() req, @Res() res: Response) {
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
      const { accessToken, isNewUser, user } = authResult as {
        accessToken: string;
        isNewUser: boolean;
        user: any;
      };

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
  refreshAccessToken(@Req() req, @Res() res: Response) {
    // Validate refreshToken and generate new access token
    return this.authService.refreshAccessToken(req, res);
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
  async logout(@Req() req: Request, @Res() res: Response) {
    console.log('logout called successfully');
    // Clear all auth cookie
    const userId = (req as any).user?.id;
    if (!userId) {
      return nestError(400, 'User not found')(res);
    }
    // await redisDeleteKey(`user_active:${userId}`);

    clearAllAuthCookies(res);
    return nestResponse(200, 'Logged out successfully')(res);
  }

  // Register
  @Post('register')
  async register(@Body() body: any, @Res() res: Response) {
    console.log('register called successfully', body);
    const email = body.email;
    const role = body.role;
    if (email.endsWith('.com')) {
      if (role !== 'civilian') {
        return nestError(400, 'your email is not fit in your role')(res);
      }
    } else if (email.endsWith('.edu')) {
      if (role !== 'student') {
        return nestError(400, 'your email is not fit in your role')(res);
      }
    } else if (email.endsWith('.mil')) {
      if (role !== 'military') {
        return nestError(400, 'your email is not fit in your role')(res);
      }
    } else {
      return nestError(400, 'your email is not fit in your role')(res);
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
      return nestError(400, 'Validation failed', messages);
    }

    if (registerDto.password !== registerDto.confirmPassword) {
      return nestError(400, 'Password and confirm password do not match');
    }

    return this.authService.register(registerDto, res as any);
  }

  // Verify OTP
  @Post('verify-otp')
  async verifyOtp(
    @Body() body: any,
    @Res() res: Response,
  ) {
    return this.authService.verifyOtp(body, res as any);
  }

  // Resend OTP
  @Post('resend-otp')
  async resendOtp(
    @Body() body: any,
    @Res() res: Response,
  ) {
    return this.authService.resendOtp(body, res as any);
  }

  // Login
  @Post('login')
  async login(@Body() body: any, @Res() res: Response) {
    console.log('login called successfully', body);
    return this.authService.login(body, res as any);
  }

  // Forgot Password
  @Post('forgot-password')
  async forgotPassword(
    @Body() body: any,
    @Res() res: Response,
  ) {
    return this.authService.forgotPassword(body, res as any);
  }

  // Reset password
  @Post('reset-password')
  async resetPassword(
    @Body() body: any,
    @Res() res: Response,
  ) {
    return this.authService.resetPassword(body, res as any);
  }
}

