import { BadRequestException, Injectable } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import * as dotenv from 'dotenv';
import { OAuthProviderType, UserRole, UserStatus } from '@prisma/client';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';
import { RegisterDto } from './dto/login.dto';
import * as bcrypt from 'bcryptjs';
import { hashPassword } from 'src/common/helpers/hashing';
import * as jwt from 'jsonwebtoken';
import { generateOTP } from 'src/common/helpers/generateOtp';
import { safeGet, safeSet } from 'src/common/lib/redis';
import { sendEmailOTP } from 'src/common/lib/nodemailer';
import { appConfig } from 'src/config/app.config';
import path from 'path';
// import { UserRole, AgentStatus } from '../../generated/prisma/enums';
dotenv.config();

@Injectable()
export class AuthService {
  constructor(private prisma: PrismaService) { }

  async checkUserEmail(email: string) {
    const user = await this.prisma.user.findUnique({
      where: {
        email: email,
      },
    });
    return user;
  }

  // Google Login
  // This is the function that is called when the user clicks the Google Login button

  async googleLogin(user: any, role: string, company: string, res: any) {
    if (!user) {
      return 'No user from Google';
    }
    const existingUser = await this.prisma.user.findUnique({
      where: {
        email: user.email,
      },
    });
    if (!existingUser) {
      const payload = {
        email: user.email,
        firstName: user.firstName,
        lastName: user.lastName,
        profileImageUrl: user.profileImageUrl,
        emailVerified: user.emailVerified,
        role: role as UserRole,
        company,
        status: UserStatus.ACTIVE,
      };





      const newUser = await this.prisma.user.create({
        data: payload,
      });

     const oAuthProvider =  await this.prisma.oAuthProvider.create({
        data: {
          provider: OAuthProviderType.google,
          providerUserId: user.providerUserId,
          userId: newUser.id,
        },
      });


      const accessToken = jwt.sign(
        { userId: newUser.id },
        appConfig.jwtSecret as string,
        { expiresIn: '1h' },
      );

      const refreshToken = jwt.sign(
        { userId: newUser.id },
        appConfig.jwtSecret as string,
        { expiresIn: '14' },
      );

      res.cookie('google_accessToken', accessToken, {
        httpOnly: true,
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') ,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        path: '/',
        maxAge: 1 * 60 * 60 * 1000, // 1 hour
        // maxAge: 1 * 60 * 1000, // 1 minute
      });
      res.cookie('google_refreshToken', refreshToken, {
        httpOnly: true,
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') ,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        path: '/',
        maxAge: 14 * 24 * 60 * 60 * 1000, // 14 days
      });

      const existingSession = await this.prisma.session.findFirst({
        where: { userId: newUser.id },
      });

      if (existingSession) {
        await this.prisma.session.update({
          where: { id: existingSession.id },
          data: {
            token: refreshToken,
            expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
            // expiresAt: new Date(Date.now() + 4 * 60 * 1000), // 4 minutes
          },
        });
        console.log('Existing session updated');
        return res.redirect(`${process.env.FRONTEND_URL}/chat`);
      } else {
        await this.prisma.session.create({
          data: {
            userId: newUser.id,
            token: refreshToken,
            expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
            // expiresAt: new Date(Date.now() + 4 * 60 * 1000), // 4 minutes
          },
        });
      }
      console.log('New session created');
      return res.redirect(`${process.env.FRONTEND_URL}/chat`);
    }
    const accessToken = jwt.sign(
        { userId: existingUser.id },
        appConfig.jwtSecret as string,
        { expiresIn: '1h' },
      );

      const refreshToken = jwt.sign(
        { userId: existingUser.id },
        appConfig.jwtSecret as string,
        { expiresIn: '14d' },
      );

      res.cookie('google_accessToken', accessToken, {
        httpOnly: true,
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax'),
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        path: '/',
        maxAge: 1 * 60 * 60 * 1000, // 1 hour
        // maxAge: 1 * 60 * 1000, // 1 minute
      });
      res.cookie('google_refreshToken', refreshToken, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
        path: '/',
        maxAge: 14 * 24 * 60 * 60 * 1000, // 14 days
        // maxAge: 4 * 60 * 1000, // 4 minutes
      });

      const existingSession = await this.prisma.session.findFirst({
        where: { userId: existingUser.id },
      });


      if (existingSession) {
        await this.prisma.session.update({
          where: { id: existingSession.id },
          data: {
            token: refreshToken,
            expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
            // expiresAt: new Date(Date.now() + 4 * 60 * 1000), // 4 minutes
          },
        });
        console.log('Existing session updated');
        return res.redirect(`${process.env.FRONTEND_URL}/chat`);
      } else {
        await this.prisma.session.create({
          data: {
            userId: existingUser.id,
            token: refreshToken,
            expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
            // expiresAt: new Date(Date.now() + 4 * 60 * 1000), // 4 minutes
          },
        });
        console.log('New session created');
        return res.redirect(`${process.env.FRONTEND_URL}/chat`);
      }

  }

  // Register
  // This is the function that is called when the user clicks the Register button
  async register(registerDto: RegisterDto, res: any) {
    // Check if user already exists

    const existingUser = await this.prisma.user.findUnique({
      where: { email: registerDto.email },
    });

    // Hash password
    const password = await hashPassword(registerDto.password);

    const payload = {
      email: registerDto.email,
      passwordHash: password,
      firstName: registerDto.firstName,
      lastName: registerDto.lastName,
      company: registerDto.company,
      role: registerDto.role,
      emailVerified: false,
      status: UserStatus.INACTIVE, // Inactive until OTP verified
    };

        if (existingUser) {
            // If user exists and is emailVerified, they already have an account
            if (existingUser.emailVerified) {
                nestError(400, 'User with this email already exists')(res);
                return;
            }
            // Update existing unverified user
            const updatedUser = await this.prisma.user.update({
                where: { email: registerDto.email },
                data: payload
            });
            if (!updatedUser) {
                nestError(500, 'Failed to update user')(res);
                return;
            }
        } else {
            // Create new user
            const newUser = await this.prisma.user.create({
                data: payload
            });
            if (!newUser) {
                nestError(500, 'Failed to create user')(res);
                return;
            }
        }

        // Generate and send OTP (for both new and updated unverified users)
        const rediskey = `otp:${registerDto.email}`;
        if(!rediskey){
            nestError(400, 'OTP not found')(res);
            return;
        }
        const otpCode = generateOTP();
        const {success,error} = await safeSet(rediskey, otpCode, 300); // 5 minutes
        if(!success){
            nestError(500, 'Failed to generate OTP', error)(res);
            return;
        }

        try {
          const result = await sendEmailOTP(registerDto.email, otpCode);
          console.log("result", result);
          if(!result.success){
            nestError(500, 'Failed to send OTP', result.message)(res);
            return;
          }
          nestResponse(200, `OTP sent successfully to this ${payload.email}`)(res);
          return;
        } catch (error) {
            nestError(500, 'Failed to send OTP', error)(res);
        }


    }

  // Verify OTP
  // This is the function that is called when the user clicks the Verify OTP button

    async verifyOtp(body: any, res: any) {
        const { email, otp } = body;
        const rediskey = `otp:${email}`;
        if(!rediskey){
            nestError(400, 'OTP not found')(res);
            return;
        }
        const otpCode = await safeGet(rediskey);
        if(!otpCode){
            nestError(400, 'OTP expired')(res);
            return;
        }
        if(otpCode.toString() !== otp.toString()){
            nestError(400, 'Invalid OTP')(res);
            return;
        }
        const user = await this.prisma.user.findUnique({
            where: { email }
        });
        if(!user){
            nestError(400, 'User not found')(res);
            return;
        }
        const refreshToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret as string, { expiresIn: '7d' });
        user.emailVerified = true;
        await this.prisma.user.update({
            where: { id: user.id },
            data: { 
                emailVerified: true,
                status: UserStatus.ACTIVE  // Set status to ACTIVE when OTP is verified
            }
        });

        await this.prisma.session.create({
            data: {
                userId: user.id,
                token: refreshToken,
                expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
            }
        });
        nestResponse(200, 'OTP verified successfully')(res);
        return;
    }

    // Resend OTP
    // This is the function that is called when the user clicks the Resend OTP button
    async resendOtp(body: any, res: any) {
        const { email } = body;
        const rediskey = `otp:${email}`;
        if(!rediskey){
            nestError(400, 'OTP not found')(res);
            return;
        }
        const otpCode = generateOTP();
        const {success,error} = await safeSet(rediskey, otpCode as string, 300); // 5 minutes
        if(!success){
            nestError(500, 'Failed to generate OTP', error)(res);
            return;
        }
        try {
            const result = await sendEmailOTP(email, otpCode as string);
            if(!result.success){
              nestError(500, 'Failed to send OTP', result.message)(res);
              return;
            }

            nestResponse(200, `OTP sent successfully to this ${email}`)(res);
            return;
          } catch (error) {

              nestError(500, 'Failed to send OTP', error)(res);
          }
    }

  // Login
  // This is the function that is called when the user clicks the Login button
  async login(body: any, res: any) {
    const { email, password } = body;
    const user = await this.prisma.user.findUnique({
      where: { email },
    });
    console.log('user', user);
    if (!user) {
      return nestError(400, 'User not found')(res);
    }
    if (!user.emailVerified) {
      return nestError(400, 'User not verified')(res);
    }
    if (!user || !user.passwordHash) {
      return nestError(400, 'Invalid password or user not found')(res);
    }
    const isPasswordValid = await bcrypt.compare(password, user?.passwordHash);
    if (!isPasswordValid) {
      return nestError(400, 'Invalid password')(res);
    }
    const accessToken = jwt.sign(
      { userId: user.id },
      appConfig.jwtSecret as string,
      { expiresIn: '1h' },
    );
    const refreshToken = jwt.sign(
      { userId: user.id },
      appConfig.jwtSecret as string,
      { expiresIn: '14d' },
    );

    // Set access token cookie
    res.cookie('local_accessToken', accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
      sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
      path: '/',
      maxAge: 60 * 60 * 1000, // 1 hour
      // maxAge: 2 * 60 * 1000, // 2 minutes
    });

    res.cookie('local_refreshToken', refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
      sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
      path: '/',
      maxAge: 14 * 24 * 60 * 60 * 1000, // 14 days
      // maxAge: 7 * 60 * 1000, // 7 minutes

    });

    // Create or update session
    const existingSession = await this.prisma.session.findFirst({
      where: { userId: user.id },
    });

    if (existingSession) {
      await this.prisma.session.update({
        where: { id: existingSession.id },
        data: {
          token: refreshToken,
          expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
          // expiresAt: new Date(Date.now() + 7  * 60 * 1000), // 7 minutes
        },
      });
    } else {
      await this.prisma.session.create({
        data: {
          userId: user.id,
          token: refreshToken,
           expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
          // expiresAt: new Date(Date.now() + 7 * 60 * 60 * 1000), // 7 minutes
        },
      });
    }
    // const userId = user.id;
    // const { success, error } = await safeSet(
    //   `user_active:${userId}`,
    //   '1',
    //   3600,
    // ); // 1 hour TTL
    // if (!success) {
    //   return nestError(500, 'Failed to set user active', error)(res);
    // }


    return nestResponse(200, 'Login successful')(res);
  }

    // Forgot Password
    // This is the function that is called when the user clicks the Forgot Password button
    async forgotPassword(body: any, res: any) {
        try {
        const { email } = body;
        if(!email){
            nestError(400, 'Email is required')(res);
            return;
        }
        const user = await this.prisma.user.findUnique({
            where: { email }
        });
        if(!user){
            nestError(400, 'User not found')(res);
            return;
        }
        if(!user.emailVerified){
            nestError(400, 'User not verified')(res);
            return;
        }
        const otpCode = generateOTP();
        const rediskey = `otp:${email}`;
        const {success,error} = await safeSet(rediskey, otpCode as string, 300); // 5 minutes
        if(!success){
            nestError(500, 'Failed to generate OTP', error)(res);
            return;
        }
            const result = await sendEmailOTP(email, otpCode as string);
            if(!result.success){
                nestError(500, 'Failed to send OTP', result.message)(res);
                return;
            }
        nestResponse(200, 'OTP sent successfully')(res);
        return;
        } catch (error) {
            nestError(500, 'Failed to send OTP', error)(res);
        }
    }

  // reset password
  // This is the function that is called when the user clicks the Reset Password button
  async resetPassword(body: any, res: any) {
    const { email, newPassword } = body;

        if(!email || !newPassword){
            nestError(400, 'Email and new password are required')(res);
            return;
        }

        const user = await this.prisma.user.findUnique({
            where: { email }
        });
        if(!user){
            nestError(400, 'User not found')(res);
            return;
        }
        if(!user.emailVerified){
            nestError(400, 'User not verified')(res);
            return;
        }
        const password = await hashPassword(newPassword);
        await this.prisma.user.update({
            where: { id: user.id },
            data: { passwordHash: password, emailVerified: true }
        });
        nestResponse(200, 'Password reset successfully')(res);
        return;
       
    }

  // refresh access token
  // This function handles token refresh for both local JWT tokens and Google OAuth tokens
 // AuthService.ts snippet
async refreshAccessToken(req: any, res: any) {
  try {
    const local_refreshToken = req.cookies?.local_refreshToken;
    const google_refreshToken = req.cookies?.google_refreshToken;

    const token = local_refreshToken || google_refreshToken;
    const isGoogle = !!google_refreshToken;

    if (!token) return nestError(401, 'No refresh token')(res);

    try {
      const decoded = jwt.verify(token, appConfig.jwtSecret as string) as any;
      
      const session = await this.prisma.session.findFirst({
        where: {
          userId: decoded.userId,
          token: token, // Strict match: DB wala token aur cookie wala same ho
          expiresAt: { gt: new Date() },
        },
      });

      if (!session) throw new Error('Invalid session');

      const user = await this.prisma.user.findUnique({ where: { id: decoded.userId } });

      const newAccessToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret, { expiresIn: '1h' });
      const newRefreshToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret, { expiresIn: '14d' });

      const tokenPrefix = isGoogle ? 'google' : 'local';

      // HAMESHA '/' path use karein login/refresh har jagah
      res.cookie(`${tokenPrefix}_accessToken`, newAccessToken, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
        path: '/', 
        maxAge: 3600000,
      });

      res.cookie(`${tokenPrefix}_refreshToken`, newRefreshToken, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
        path: '/', // Isko '/' hi rakhein taaki purani delete ho jaye
        maxAge: 14 * 24 * 60 * 60 * 1000,
      });

      await this.prisma.session.update({
        where: { id: session.id },
        data: {
          token: newRefreshToken,
          expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
        },
      });

      return nestResponse(200, 'Refreshed', { refreshed: true })(res);
    } catch (e) {
      // Clear all possible cookies on failure
      const options = { path: '/', httpOnly: true };
      res.clearCookie('local_refreshToken', options);
      res.clearCookie('google_refreshToken', options);
      return nestError(401, 'Session Expired')(res);
    }
  } catch (error) {
    return nestError(500, 'Internal Server Error')(res);
  }
}
}