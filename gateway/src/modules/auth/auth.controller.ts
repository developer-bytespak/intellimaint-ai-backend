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

import { Controller, Get, UseGuards, Req, UnauthorizedException, Post, Res, Next } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { AuthService } from './auth.service';
import type { Response, Request } from 'express';
import { JwtAuthGuard } from './jwt-auth.guard';
import * as jwt from 'jsonwebtoken';
import * as passport from 'passport';
import { nestResponse } from 'src/common/helpers/responseHelpers';
import { GoogleAuthGuard } from './google-auth.guard';

// AuthController;

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) { }
  @Get('google')
  @UseGuards(GoogleAuthGuard)
  googleAuth(@Req() req: Request, @Res() res: Response, @Next() next) {
    const token = req.cookies?.jwt;

    if (token) {
      try {
        return res.redirect('http://localhost:3000/dashboard');
      } catch (e) {
        res.clearCookie('jwt', {
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax',
          path: '/',
        });
      }
    }
    const passportInstance = (req as any)._passport?.instance || require('passport');

    passportInstance.authenticate('google', {
      scope: ['email', 'profile'],
      prompt: 'consent',
      accessType: 'offline'
    } as any)(req, res, next);
  }

  @Get('google/redirect')
  @UseGuards(AuthGuard('google'))
  async googleRedirect(@Req() req, @Res({ passthrough: true }) res: Response) {
    console.log("googleRedirect called successfully");
    const authResult = await this.authService.googleLogin(req.user);
    const { accessToken, isNewUser, user } = authResult as { accessToken: string, isNewUser: boolean, user: any };
    res.cookie('jwt', accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      maxAge: 2 * 60 * 60 * 1000, // 2 hours
    });
    if (!isNewUser) {
      return nestResponse(201, 'User created successfully', user)(res);
    }
    return nestResponse(200, 'Login successful', user)(res);
  }

  @Post('refresh')
  refreshAccessToken(@Req() req, @Res({ passthrough: true }) res: Response) {
    const refreshToken = req.cookies.refresh_token;

    // Validate refreshToken and generate new access token
    const newAccessToken = 'NEW_DUMMY_JWT';

    res.cookie('jwt', newAccessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      maxAge: 2 * 60 * 60 * 1000, // 2 hours
    });

    return { message: 'Access token refreshed successfully' };
  }

  @UseGuards(JwtAuthGuard)
  @Get('profile')
  getProfile(@Req() req) {
    return {
      message: 'User authenticated!',
      user: req.user,
    };
  }


  @Get('logout')
  logout(@Res({ passthrough: true }) res: Response) {
    console.log("logout called successfully");
    res.clearCookie('jwt', { httpOnly: true, sameSite: 'lax', path: '/' });
    return { message: 'Logged out successfully' };
  }




}






