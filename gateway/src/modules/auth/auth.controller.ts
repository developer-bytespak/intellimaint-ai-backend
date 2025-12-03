// import { Controller, Post, Body, UseGuards } from '@nestjs/common';
// import { AuthService } from './auth.service'; 

// @Controller('auth')
// export class AuthController {
//   constructor(private authService: AuthService) {}

//   @Post('login')
//   async login(@Body() loginDto: any) {
//     return this.authService.login(loginDto);
//   }

//   @Post('register')
//   async register(@Body() registerDto: any) {
//     return this.authService.register(registerDto);
//   }
// }

import { Controller, Get, UseGuards, Req, UnauthorizedException, Post, Res, Next, Body } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { AuthService } from './auth.service';
import type { Response, Request } from 'express';
import { JwtAuthGuard } from './jwt-auth.guard';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';
import { GoogleAuthGuard } from './google-auth.guard';
import { RegisterDto } from './dto/login.dto';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import { redisDeleteKey } from 'src/common/lib/redis';

// AuthController;

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) { }

  // Google Login
  // This is the first endpoint that is called when the user clicks the Google Login button
  @Get('google')
  // @UseGuards(GoogleAuthGuard)
  googleAuth(@Req() req: Request, @Res() res: Response, @Next() next) {
    const googleToken = req.cookies?.google_access;
    const localToken = req.cookies?.local_access;
    const role = (req as any).query.role as string;
    const company = (req as any).query.company as string;
    
    // If user already has a valid token, redirect to chat
    if (googleToken || localToken) {
      try {
        return res.redirect(`${process.env.FRONTEND_URL}/chat`);
      } catch (e) {
        // Clear cookies if there's an error
        res.clearCookie('google_access', {
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax',
          path: '/',
        });
        res.clearCookie('local_access', {
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax',
          path: '/',
        });
      }
    }
    const passportInstance = (req as any)._passport?.instance || require('passport');

    return passportInstance.authenticate('google', {
      scope: ['email', 'profile'],
      prompt: 'consent',
      accessType: 'offline',
      state: JSON.stringify({ role, company }),
    } as any)(req, res, next);
  }

  @Get('google/redirect')
  @UseGuards(AuthGuard('google'))
  async googleRedirect(@Req() req, @Res({ passthrough: true }) res: Response) {
    const { role, company } = JSON.parse(req.query.state as string);
    // console.log("role", role);
    // console.log("company", company);

    const email = req.user.email;

    if (email.endsWith('.com')) {
      if (role !== 'civilian') {
        return res.redirect(`${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`);
      }
    } else if (email.endsWith('.edu')) {
      if (role !== 'student') {
        return res.redirect(`${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`);
      }
    } else if (email.endsWith('.mil')) {
      if (role !== 'military') {
        return res.redirect(`${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`);
      }
    } else {
      return res.redirect(`${process.env.FRONTEND_URL}/callback?error=Your Email is not fit in your role`);
    }


    const authResult = await this.authService.googleLogin(req.user, role, company);
    const { accessToken, isNewUser, user } = authResult as { accessToken: string, isNewUser: boolean, user: any };
    
    // Set Google access token cookie
    res.cookie('google_access', accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 1 * 60 * 60 * 1000, // 1 hours
    });
    
    // Set user email cookie for refresh token logic
    res.cookie('google_user_email', user.email, {
      httpOnly: false, // Not httpOnly so guard can read it for refresh
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 1 * 60 * 60 * 1000, // 1 hours
    });

    // if (!isNewUser) {
    //   return nestResponse(201, 'User created successfully', user)(res);
    // }
    // return nestResponse(200, 'Login successful', user)(res);
    return res.redirect(`${process.env.FRONTEND_URL}/chat`)
  }

  @Post('refresh')
  refreshAccessToken(@Req() req, @Res({ passthrough: true }) res: Response) {

    // Validate refreshToken and generate new access token

    return this.authService.refreshAccessToken(res as any);

    
  }

  @UseGuards(JwtAuthGuard)
  @Get('profile')
  getProfile(@Req() req) {
    return {
      message: 'User authenticated!',
      user: req.user,
    };
  }

  // Logout
  // This is the endpoint that is called when the user clicks the Logout button
  @UseGuards(JwtAuthGuard)
  @Get('logout')
  async logout(@Req() req: Request, @Res({ passthrough: true }) res: Response) {
    console.log("logout called successfully");
    // Clear all auth cookie
    const userId = (req as any).user?.id;
    if(!userId){
      return nestError(400, 'User not found')(res);
    }
    await redisDeleteKey(`user_active:${userId}`);
    
    res.clearCookie('local_access', { httpOnly: true, sameSite: 'lax', path: '/' });
    res.clearCookie('google_access', { httpOnly: true, sameSite: 'lax', path: '/' });
    res.clearCookie('refresh_token', { httpOnly: true, sameSite: 'lax', path: '/' });
    res.clearCookie('google_user_email', { httpOnly: false, sameSite: 'lax', path: '/' });
    res.redirect(`${process.env.FRONTEND_URL}/login`);
    return { message: 'Logged out successfully' };
  }

  // Register
  // This is the endpoint that is called when the user clicks the Register button
  @Post('register')
  async register(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    console.log("register called successfully", body);
    const email = body.email;
    const role = body.role;
    if (email.endsWith('.com')) {
      if (role !== 'civilian') {
        return nestError(400,"your email is not fit in your role")(res);
      }
    } else if (email.endsWith('.edu')) {
      if (role !== 'student') {
        return nestError(400,"your email is not fit in your role")(res);
      }
    } else if (email.endsWith('.mil')) {
      if (role !== 'military') {
        return nestError(400,"your email is not fit in your role")(res);
      }
    } else {
      return nestError(400,"your email is not fit in your role")(res);
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
    const messages = errors.map(err => Object.values(err.constraints || {})).flat();
    return nestError(400, 'Validation failed', messages);
  }

  if(registerDto.password !== registerDto.confirmPassword){
    return nestError(400, 'Password and confirm password do not match');
  }

    return this.authService.register(registerDto, res as any);
  }

  // Verify OTP
  // This is the function that is called when the user clicks the Verify OTP button
  @Post('verify-otp')
  async verifyOtp(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    return this.authService.verifyOtp(body, res as any);
  }

  // Resend OTP
  // This is the function that is called when the user clicks the Resend OTP button

  @Post('resend-otp')
  async resendOtp(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    return this.authService.resendOtp(body, res as any);
  }

  // Login
  @Post('login')
  async login(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    console.log("login called successfully", body);
    return  this.authService.login(body, res as any);
    
  }

  // Forgot Password
  // This is the endpoint that is called when the user clicks the Forgot Password button
  @Post('forgot-password')
  async forgotPassword(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    return this.authService.forgotPassword(body, res as any);
  }

  // reset password
  // This is the endpoint that is called when the user clicks the Reset Password button
  @Post('reset-password')
  async resetPassword(@Body() body: any, @Res({ passthrough: true }) res: Response) {
    return this.authService.resetPassword(body, res as any);
  }




}






