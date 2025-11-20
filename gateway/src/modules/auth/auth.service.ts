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
// import { UserRole, AgentStatus } from '../../generated/prisma/enums';
dotenv.config();

@Injectable()
export class AuthService {
    constructor(private prisma: PrismaService) { }

    // Google Login
    // This is the function that is called when the user clicks the Google Login button

    async googleLogin(user: any, role: string, company: string) {
        if (!user) {
            return 'No user from Google';
        }
        const existingUser = await this.prisma.user.findUnique({
            where: {
                email: user.email
            }
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
                status: UserStatus.INACTIVE,
            }
            const newUser = await this.prisma.user.create({
                data: {
                    ...payload,
                    oauthProviders: {
                        create: {
                            provider: OAuthProviderType.google,
                            providerUserId: user.id,
                            refreshToken: user.refreshToken,
                            tokenExpiresAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30), // 30 days
                        }
                    }
                }
            });

            if (newUser) {
                return { user: newUser, accessToken: user.accessToken, isNewUser: false };
            }
            return nestResponse(500, 'Failed to create user', null);
        }

        return { user: existingUser, accessToken: user.accessToken, isNewUser: true };







    }

    // Register
    // This is the function that is called when the user clicks the Register button
    async register(registerDto: RegisterDto, res: any) {
        // Check if user already exists
        const existingUser = await this.prisma.user.findUnique({
            where: { email: registerDto.email }
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

        }

        if (existingUser) {
            if (existingUser.emailVerified) {
                return nestError(400, 'User with this email already exists')(res);
            }
            // Update existing unverified user
            const updatedUser = await this.prisma.user.update({
                where: { email: registerDto.email },
                data: payload
            });
            if (!updatedUser) {
                return nestError(500, 'Failed to update user')(res);
            }
        } else {
            // Create new user
            const newUser = await this.prisma.user.create({
                data: payload
            });
            if (!newUser) {
                return nestError(500, 'Failed to create user')(res);
            }
        }

        // Generate and send OTP (for both new and updated unverified users)
        const rediskey = `otp:${registerDto.email}`;
        const otpCode = generateOTP();
        // const {success,error} = await safeSet(rediskey, otpCode, 5);
        // if(!success){
        //     return nestError(500, 'Failed to generate OTP', error)(res);
        // }

        try {
          const result = await sendEmailOTP(registerDto.email, otpCode);
          console.log("result", result);
          if(!result.success){
            return nestError(500, 'Failed to send OTP', result.message)(res);
          }
          return nestResponse(200, `OTP sent successfully to this ${payload.email}`)(res);
        } catch (error) {
            return nestError(500, 'Failed to send OTP', error)(res);
        }


    }

    // Verify OTP
    // This is the function that is called when the user clicks the Verify OTP button

    async verifyOtp(body: any, res: any) {
        const { email, otp } = body;
        const rediskey = `otp:${email}`;
        const otpCode = await safeGet(rediskey);
        if(!otpCode){
            return nestError(400, 'OTP expired')(res);
        }
        if(otpCode !== otp){
            return nestError(400, 'Invalid OTP')(res);
        }
        const user = await this.prisma.user.findUnique({
            where: { email }
        });
        if(!user){
            return nestError(400, 'User not found');
        }
        const refreshToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret as string, { expiresIn: '7d' });
        user.emailVerified = true;
        await this.prisma.user.update({
            where: { id: user.id },
            data: { emailVerified: true }
        });

        await this.prisma.session.create({
            data: {
                userId: user.id,
                token: refreshToken,
                expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
            }
        });
        return nestResponse(200, 'OTP verified successfully')(res);
    }

    // Resend OTP
    // This is the function that is called when the user clicks the Resend OTP button
    async resendOtp(body: any, res: any) {
        const { email } = body;
        const rediskey = `otp:${email}`;
        const otpCode = await safeGet(rediskey);
        if(!otpCode){
            return nestError(400, 'OTP expired')(res);
        }
        const {success,error} = await safeSet(rediskey, otpCode, 5);
        if(!success){
            return nestError(500, 'Failed to generate OTP', error)(res);
        }
        try {
            const result = await sendEmailOTP(email, otpCode);
            if(!result.success){
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
            where: { email }
        });
        console.log("user", user);
        if(!user){
            return nestError(400, 'User not found')(res);
        }
        if(!user.emailVerified){
            return nestError(400, 'User not verified')(res);
        }
        if (!user || !user.passwordHash) {
            return nestError(400, 'Invalid password or user not found')(res);
          }
        const isPasswordValid = await bcrypt.compare(password, user?.passwordHash);
        if(!isPasswordValid){
            return nestError(400, 'Invalid password')(res);
        }
        const accessToken = jwt.sign({ userId: user.id }, appConfig.jwtSecret as string, { expiresIn: '1h' });
        res.cookie('jwt', accessToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            maxAge: 3 * 60 * 60 * 1000, // 3 hour
        });
        return nestResponse(200, 'Login successful')(res);
    }

}

