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
import { otpExpiry } from 'src/common/helpers/otpExpiry';
import { safeGet, safeSet } from 'src/common/lib/redis';
import { sendEmailOTP } from 'src/common/lib/nodemailer';
import { appConfig } from 'src/config/app.config';
import axios from 'axios';
// import { UserRole, AgentStatus } from '../../generated/prisma/enums';
dotenv.config();

@Injectable()
export class AuthService {
  constructor(private prisma: PrismaService) {}

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
        data: {
          ...payload,
          oauthProviders: {
            create: {
              provider: OAuthProviderType.google,
              providerUserId: user.id,
              refreshToken: user.refreshToken,
              tokenExpiresAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30), // 30 days
            },
          },
        },
      });

            if (!newUser) {
                throw new BadRequestException('Failed to create user');
            }
            return { user: newUser, accessToken: user.accessToken, isNewUser: false };
        }
        await this.prisma.oAuthProvider.updateMany({
            where: {
                provider: OAuthProviderType.google,
                userId: existingUser.id,
            },
            data: {
                refreshToken: user.refreshToken,
                tokenExpiresAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 60), // 60 days expiry
            }
        });

    return {
      user: existingUser,
      accessToken: user.accessToken,
      isNewUser: true,
    };
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
            where: { email }
        });
        console.log("user", user);
        if(!user){
            nestError(400, 'User not found')(res);
            return;
        }
        if(!user.emailVerified){
            nestError(400, 'User not verified')(res);
            return;
        }
        if(user.status !== UserStatus.ACTIVE){
            nestError(400, 'User account is not active. Please contact support.')(res);
            return;
        }
        if (!user || !user.passwordHash) {
            nestError(400, 'Invalid password or user not found')(res);
            return;
          }
        const isPasswordValid = await bcrypt.compare(password, user?.passwordHash);
        if(!isPasswordValid){
            nestError(400, 'Invalid password')(res);
            return;
        }
        const accessToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret as string, { expiresIn: '1h' });
        const refreshToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret as string, { expiresIn: '7d' });
        
        const cookieOptions = {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
            sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
            path: '/',
            maxAge: 60 * 60 * 1000, // 1 hour
        };
        
        console.log('Setting local_access cookie with options:', {
            ...cookieOptions,
            nodeEnv: process.env.NODE_ENV,
            forceSecure: process.env.FORCE_SECURE_COOKIES,
        });
        
        // Set access token cookie with proper CORS settings
        res.cookie('local_access', accessToken, cookieOptions);
        
       
        
        // Create or update session
        const existingSession = await this.prisma.session.findFirst({
            where: { userId: user.id },
        });
        
        if (existingSession) {
            await this.prisma.session.update({
                where: { id: existingSession.id },
                data: {
                    token: refreshToken,
                    expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
                },
            });
        } else {
            await this.prisma.session.create({
                data: {
                    userId: user.id,
                    token: refreshToken,
                    expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
                },
            });
        }
        const userId = user.id;
       const {success,error} = await safeSet(`user_active:${userId}`, "1", 3600); // 1 hour TTL
       if(!success){
        nestError(500, 'Failed to set user active', error)(res);
        return;
       }

        
        nestResponse(200, 'Login successful')(res);
        return;
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
  async refreshAccessToken(req: any, res: any) {
    try {
      const localToken = req.cookies?.local_access;
      const googleToken = req.cookies?.google_access;
      const googleEmail = req.cookies?.google_user_email;

            // ==============================
            // CASE 1: LOCAL TOKEN REFRESH
            // ==============================
            if (localToken) {
                try {
                    let userId: string;
                    
                    // Try to decode token (even if expired) to get userId
                    try {
                        const decoded = jwt.verify(localToken, appConfig.jwtSecret as string) as any;
                        userId = decoded.userId;
                    } catch (error) {
                        // Token is expired or invalid, try to decode without verification to get userId
                        const decoded = jwt.decode(localToken) as any;
                        if (!decoded || !decoded.userId) {
                            res.clearCookie('local_access');
                            nestError(401, 'Invalid token format')(res);
                            return;
                        }
                        userId = decoded.userId;
                    }
                    
                    // Find user's session with refresh token
                    const session = await this.prisma.session.findFirst({
                        where: {
                            userId: userId,
                            expiresAt: { gt: new Date() } // Session must still be valid
                        },
                    });

                    if (!session) {
                        res.clearCookie('local_access');
                        nestError(401, 'Session not found or expired')(res);
                        return;
                    }

                    // Verify refresh token
                    try {
                        jwt.verify(session.token, appConfig.jwtSecret as string);
                    } catch (error) {
                        // Refresh token expired
                        res.clearCookie('local_access');
                        nestError(401, 'Refresh token expired')(res);
                        return;
                    }

          // Get user to verify they still exist and are verified
          const user = await this.prisma.user.findUnique({
            where: { id: userId },
          });

                    if (!user) {
                        res.clearCookie('local_access');
                        nestError(401, 'User not found')(res);
                        return;
                    }

                    if (!user.emailVerified) {
                        nestError(403, 'User not verified')(res);
                        return;
                    }

          // Generate new access token
          const newAccessToken = jwt.sign(
            { userId: user.id },
            appConfig.jwtSecret as string,
            { expiresIn: '1h' },
          );

                    // Update cookie with new access token
                    res.cookie('local_access', newAccessToken, {
                        httpOnly: true,
                        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
                        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
                        path: '/',
                        maxAge: 60 * 60 * 1000, // 1 hour
                    });

          // Mark user as active in Redis
          const activeUserKey = `user_active:${user.id}`;
          await safeSet(activeUserKey, '1', 900); // 15 minutes TTL

                    nestResponse(200, 'Token refreshed successfully', { refreshed: true })(res);
                    return;
                } catch (error) {
                    res.clearCookie('local_access');
                    nestError(401, 'Invalid or expired token')(res);
                    return;
                }
            }

      // ==============================
      // CASE 2: GOOGLE TOKEN REFRESH
      // ==============================
      if (googleToken && googleEmail) {
        try {
          // Find user by email
          const user = await this.prisma.user.findUnique({
            where: { email: googleEmail },
            include: {
              oauthProviders: {
                where: { provider: 'google' },
              },
            },
          });

                    if (!user) {
                        res.clearCookie('google_access');
                        res.clearCookie('google_user_email');
                        nestError(401, 'User not found')(res);
                        return;
                    }

                    const provider = user.oauthProviders?.[0];
                    if (!provider?.refreshToken) {
                        res.clearCookie('google_access');
                        res.clearCookie('google_user_email');
                        nestError(401, 'Refresh token not found')(res);
                        return;
                    }

          // Call Google API to refresh access token
          const refreshRes = await axios.post(
            'https://oauth2.googleapis.com/token',
            {
              client_id: process.env.GOOGLE_CLIENT_ID,
              client_secret: process.env.GOOGLE_CLIENT_SECRET,
              refresh_token: provider.refreshToken,
              grant_type: 'refresh_token',
            },
          );

          const newAccessToken = refreshRes.data.access_token;

                    // Update cookie with new access token
                    res.cookie('google_access', newAccessToken, {
                        httpOnly: true,
                        secure: process.env.NODE_ENV === 'production' || process.env.FORCE_SECURE_COOKIES === 'true',
                        sameSite: (process.env.NODE_ENV === 'production' ? 'none' : 'lax') as 'none' | 'lax',
                        path: '/',
                        maxAge: 2 * 60 * 60 * 1000, // 2 hours
                    });

          // Mark user as active in Redis
          const activeUserKey = `user_active:${user.id}`;
          await safeSet(activeUserKey, '1', 900); // 15 minutes TTL

                    nestResponse(200, 'Token refreshed successfully', { refreshed: true })(res);
                    return;
                } catch (error) {
                    console.error('Google token refresh failed:', error.message);
                    res.clearCookie('google_access');
                    res.clearCookie('google_user_email');
                    nestError(401, 'Failed to refresh token')(res);
                    return;
                }
            }

            // ==============================
            // NO TOKEN FOUND
            // ==============================
            nestError(401, 'No valid token found')(res);
        } catch (error) {
            console.error('Token refresh error:', error);
            nestError(500, 'Internal server error during token refresh')(res);
        }
    }

}
