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
        sameSite: 'lax',
        secure: process.env.NODE_ENV === 'production',
        path: '/',
        maxAge: 1 * 60 * 60 * 1000, // 1 hour
        // maxAge: 1 * 60 * 1000, // 1 minute
      });
      res.cookie('google_refreshToken', refreshToken, {
        httpOnly: true,
        sameSite: 'lax',
        secure: process.env.NODE_ENV === 'production',
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
        sameSite: 'lax',
        secure: process.env.NODE_ENV === 'production',
        path: '/',
        maxAge: 1 * 60 * 60 * 1000, // 1 hour
        // maxAge: 1 * 60 * 1000, // 1 minute
      });
      res.cookie('google_refreshToken', refreshToken, {
        httpOnly: true,
        sameSite: 'lax',
        secure: process.env.NODE_ENV === 'production',
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
        return nestError(400, 'User with this email already exists')(res);
      }
      // Update existing unverified user
      const updatedUser = await this.prisma.user.update({
        where: { email: registerDto.email },
        data: payload,
      });
      if (!updatedUser) {
        return nestError(500, 'Failed to update user')(res);
      }
    } else {
      // Create new user
      const newUser = await this.prisma.user.create({
        data: payload,
      });
      if (!newUser) {
        return nestError(500, 'Failed to create user')(res);
      }
    }

    // Generate and send OTP (for both new and updated unverified users)
    const rediskey = `otp:${registerDto.email}`;
    if (!rediskey) {
      return nestError(400, 'OTP not found')(res);
    }
    const otpCode = generateOTP();
    const { success, error } = await safeSet(rediskey, otpCode, 300); // 5 minutes
    if (!success) {
      return nestError(500, 'Failed to generate OTP', error)(res);
    }

    try {
      const result = await sendEmailOTP(registerDto.email, otpCode);
      console.log('result', result);
      if (!result.success) {
        return nestError(500, 'Failed to send OTP', result.message)(res);
      }
      return nestResponse(
        200,
        `OTP sent successfully to this ${payload.email}`,
      )(res);
    } catch (error) {
      return nestError(500, 'Failed to send OTP', error)(res);
    }
  }

  // Verify OTP
  // This is the function that is called when the user clicks the Verify OTP button

  async verifyOtp(body: any, res: any) {
    const { email, otp } = body;
    const rediskey = `otp:${email}`;
    if (!rediskey) {
      return nestError(400, 'OTP not found')(res);
    }
    const otpCode = await safeGet(rediskey);
    if (!otpCode) {
      return nestError(400, 'OTP expired')(res);
    }
    if (otpCode.toString() !== otp.toString()) {
      return nestError(400, 'Invalid OTP')(res);
    }
    const user = await this.prisma.user.findUnique({
      where: { email },
    });
    if (!user) {
      return nestError(400, 'User not found');
    }
    const refreshToken = jwt.sign(
      { userId: user.id },
      appConfig.jwtSecret as string,
      { expiresIn: '7d' },
    );
    user.emailVerified = true;
    await this.prisma.user.update({
      where: { id: user.id },
      data: { emailVerified: true },
    });

    await this.prisma.session.create({
      data: {
        userId: user.id,
        token: refreshToken,
        expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
      },
    });
    return nestResponse(200, 'OTP verified successfully')(res);
  }

  // Resend OTP
  // This is the function that is called when the user clicks the Resend OTP button
  async resendOtp(body: any, res: any) {
    const { email } = body;
    const rediskey = `otp:${email}`;
    if (!rediskey) {
      return nestError(400, 'OTP not found')(res);
    }
    const otpCode = generateOTP();
    const { success, error } = await safeSet(rediskey, otpCode as string, 300); // 5 minutes
    if (!success) {
      return nestError(500, 'Failed to generate OTP', error)(res);
    }
    try {
      const result = await sendEmailOTP(email, otpCode as string);
      if (!result.success) {
        return nestError(500, 'Failed to send OTP', result.message)(res);
      }

      return nestResponse(200, `OTP sent successfully to this ${email}`)(res);
    } catch (error) {
      return nestError(500, 'Failed to send OTP', error)(res);
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
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60 * 1000, // 1 hour
      // maxAge: 2 * 60 * 1000, // 2 minutes
    });

    res.cookie('local_refreshToken', refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
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
      if (!email) {
        return nestError(400, 'Email is required')(res);
      }
      const user = await this.prisma.user.findUnique({
        where: { email },
      });
      if (!user) {
        return nestError(400, 'User not found')(res);
      }
      if (!user.emailVerified) {
        return nestError(400, 'User not verified')(res);
      }
      const otpCode = generateOTP();
      const rediskey = `otp:${email}`;
      const { success, error } = await safeSet(
        rediskey,
        otpCode as string,
        300,
      ); // 5 minutes
      if (!success) {
        return nestError(500, 'Failed to generate OTP', error)(res);
      }
      const result = await sendEmailOTP(email, otpCode as string);
      if (!result.success) {
        return nestError(500, 'Failed to send OTP', result.message)(res);
      }
      return nestResponse(200, 'OTP sent successfully')(res);
    } catch (error) {
      return nestError(500, 'Failed to send OTP', error)(res);
    }
  }

  // reset password
  // This is the function that is called when the user clicks the Reset Password button
  async resetPassword(body: any, res: any) {
    const { email, newPassword } = body;

    if (!email || !newPassword) {
      return nestError(400, 'Email and new password are required')(res);
    }

    const user = await this.prisma.user.findUnique({
      where: { email },
    });
    if (!user) {
      return nestError(400, 'User not found')(res);
    }
    if (!user.emailVerified) {
      return nestError(400, 'User not verified')(res);
    }
    const password = await hashPassword(newPassword);
    await this.prisma.user.update({
      where: { id: user.id },
      data: { passwordHash: password, emailVerified: true },
    });
    return nestResponse(200, 'Password reset successfully')(res);
  }

  // refresh access token
  // This function handles token refresh for both local JWT tokens and Google OAuth tokens
  async refreshAccessToken(req: any, res: any) {
    try {
      const local_refreshToken = req.cookies?.local_refreshToken;
      const google_refreshToken = req.cookies?.google_refreshToken;

      // ==============================
      // CASE 1: LOCAL TOKEN REFRESH
      // ==============================
      if (local_refreshToken) {
        try {

          // Try to decode token (even if expired) to get userId
          const decoded = jwt.verify(
            local_refreshToken,
            appConfig.jwtSecret as string,
          ) as any;
          const userId = decoded.userId;

          // Find user's session with refresh token
          const session = await this.prisma.session.findFirst({
            where: {
              userId: userId,
              expiresAt: { gt: new Date() }, // Session must still be valid
            },
          });

          if (!session) {
            res.clearCookie('local_refreshToken', { path: '/auth/refresh' });
            return nestError(401, 'Session not found or expired')(res);
          }

          if (session.token !== local_refreshToken) {
            console.log('Invalid session token');
            res.clearCookie('local_refreshToken', { path: '/auth/refresh' });
            return nestError(401, 'Invalid session token')(res);
          }

          const user = await this.prisma.user.findUnique({
            where: { id: userId },
          });



          // Generate new access token
          const newAccessToken = jwt.sign(
            { userId: user.id },
            appConfig.jwtSecret as string,
            { expiresIn: '1h' },
          );

          const newRefreshToken = jwt.sign(
            { userId: user.id },
            appConfig.jwtSecret as string,
            { expiresIn: '14d' },
          );

          // Update cookie with new access token
          res.cookie('local_accessToken', newAccessToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            path: "/",
            maxAge: 60 * 60 * 1000, // 1 hour
            // maxAge: 2 * 60 * 1000, // 2 minutes
          });

          res.cookie('local_refreshToken', newRefreshToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            path: '/auth/refresh',
            maxAge: 14 * 24 * 60 * 60 * 1000, // 14 days
            // maxAge: 7 * 60 * 1000, // 7 minutes
          });

          await this.prisma.session.update({
            where: { id: session.id },
            data: {
              token: newRefreshToken,
              expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
              // expiresAt: new Date(Date.now() + 7  * 60 * 1000), // 7 minutes
            },
          });

          console.log('Token refreshed successfully');


          return nestResponse(200, 'Token refreshed successfully', {
            refreshed: true,
          })(res);
        } catch (error) {
          res.clearCookie('local_refreshToken', { path: '/auth/refresh' });
          return nestError(401, 'Invalid or expired token')(res);
        }
      }

      // ==============================
      // CASE 2: GOOGLE TOKEN REFRESH
      // ==============================
      if (google_refreshToken) {
        try {
          // Find user by email
          const decodeGoogleToken = jwt.verify(google_refreshToken, appConfig.jwtSecret as string) as any;
          const userId = decodeGoogleToken.userId;

          const session = await this.prisma.session.findFirst({
            where: {
              userId: userId,
              expiresAt: { gt: new Date() }, // Session must still be valid
            },
          });

          if (!session) {
            res.clearCookie('google_refreshToken',{ path: '/auth/refresh' });
            return nestError(401, 'Session not found or expired')(res);
          }

          if (session.token !== google_refreshToken) {
            res.clearCookie('google_refreshToken',{ path: '/auth/refresh' });
            return nestError(401, 'Invalid session token')(res);
          }

          const user = await this.prisma.user.findUnique({
            where: { id: userId },
          });

          if (!user) {
            return nestError(401, 'User not found')(res);
          }

          const newAccessToken = jwt.sign(
            { userId: user.id },
            appConfig.jwtSecret as string,
            { expiresIn: '1h' },
          );

          const newRefreshToken = jwt.sign(
            { userId: user.id },
            appConfig.jwtSecret as string,
            { expiresIn: '14d' },
          );

          // Update cookie with new access token
          res.cookie('google_accessToken', newAccessToken, {
            httpOnly: true,
            sameSite: 'lax',
            secure: process.env.NODE_ENV === 'production',
            path: '/',
            maxAge: 1 * 60 * 60 * 1000, // 1 hour
            // maxAge: 1 * 60 * 1000, // 1 minute
          });

          res.cookie('google_refreshToken', newRefreshToken, {
            httpOnly: true,
            sameSite: 'lax',
            secure: process.env.NODE_ENV === 'production',
            path: '/auth/refresh',
            maxAge: 14 * 24 * 60 * 60 * 1000, // 14 days
            // maxAge: 4 * 60 * 1000, // 4 minutes
          });

           await this.prisma.session.update({
            where: { id: session.id },
            data: {
              token: newRefreshToken,
              /* The code is setting the `expiresAt` property to a date that is 14 days in the future
              from the current date and time. The calculation is done by adding 14 days worth of
              milliseconds to the current timestamp using `Date.now()`. */
              expiresAt: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
              // expiresAt: new Date(Date.now() + 4 * 60 * 1000), // 4 minutes
            },
          });


          return nestResponse(200, 'Token refreshed successfully', {
            refreshed: true,
          })(res);
        } catch (error) {
          console.error('Google token refresh failed:', error.message);
          res.clearCookie('google_refreshToken',{ path: '/auth/refresh' });
          return nestError(401, 'Failed to refresh token')(res);
        }
      }

      // ==============================
      // NO TOKEN FOUND
      // ==============================

      console.log("Unauthorized: No refresh token provided");
      return nestError(401, 'Unauthorized')(res);
    } catch (error) {
      console.error('Token refresh error:', error);
      return nestError(500, 'Internal server error during token refresh')(res);
    }
  }
}
