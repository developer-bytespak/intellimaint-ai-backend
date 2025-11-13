import { Injectable } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service'; 
import * as dotenv from 'dotenv';
import { asyncHandler } from '../../common/helpers/asyncHandler';
import { OAuthProviderType, UserRole, UserStatus } from '@prisma/client';
import { nestResponse } from 'src/common/helpers/responseHelpers';
// import { UserRole, AgentStatus } from '../../generated/prisma/enums';
dotenv.config();

@Injectable()
export class AuthService {
    constructor(private prisma: PrismaService) { }
    login(email: string, password: string) {
        return 'Login successful';
    };
    async googleLogin(user: any) {
        console.log("user", user);
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
                role: UserRole.civilian,
                status: UserStatus.ACTIVE,
            }
            const newUser = await this.prisma.user.create({
                data:{
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

            if(newUser) {
                return {user:newUser, accessToken: user.accessToken, isNewUser: false};
            }
            return nestResponse(500, 'Failed to create user', null);
        }

        return {user:existingUser, accessToken: user.accessToken, isNewUser: true};

        





    }

}

