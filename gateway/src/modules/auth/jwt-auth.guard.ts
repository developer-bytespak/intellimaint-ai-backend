import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import axios from 'axios';
import { Response } from 'express';
import * as jwt from 'jsonwebtoken';
import { PrismaService } from 'prisma/prisma.service';
import { appConfig } from 'src/config/app.config';
import { safeGet, redisDeleteKey, safeSet } from 'src/common/lib/redis';


@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(private prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const res: Response = context.switchToHttp().getResponse();

    const googleToken = req.cookies?.google_access;
    const localToken = req.cookies?.local_access;
    const googleEmail = req.cookies?.google_user_email;

    // Check if this is an API request (not a browser redirect)
    const isApiRequest = req.method !== 'GET' || req.headers.accept?.includes('application/json');

    // ==============================
    // CASE 1: LOCAL TOKEN
    // ==============================
    if (localToken) {
      try {
        const data = jwt.verify(localToken, appConfig.jwtSecret as string) as any;

        const user = await this.prisma.user.findUnique({
          where: { id: data.userId },
        });
        // console.log("user ==>", user);

        if (!user) throw new Error("User not found");

        // Mark user as active in Redis (15 minutes TTL)
        // This is used by the cron job to only refresh tokens for online users
        const activeUserKey = `user_active:${user.id}`;
       const {success,error}= await safeSet(activeUserKey, '1', 900); // 15 minutes TTL
       if(!success){
        console.log("Error marking user as active:", error);
       }

        // Check if there's a pending access token in Redis (from cron job)
        const pendingTokenKey = `pending_access_token:${user.id}`;
        const pendingToken = await safeGet(pendingTokenKey);
        
        if (pendingToken && typeof pendingToken === 'string') {
          // Update cookie with new token from cron job
          res.cookie('local_access', pendingToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            maxAge: 60 * 60 * 1000, // 1 hour
          });
          
          // Delete the pending token from Redis after using it
          await redisDeleteKey(pendingTokenKey);
        }

        req.user = user;
        return true;
      } catch (e) {
        res.clearCookie("local_access");
        if (isApiRequest) {
          throw new UnauthorizedException('Invalid or expired token');
        }
        res.redirect(`${process.env.FRONTEND_URL}/login`);
        return false;
      }
    }

    // ==============================
    // CASE 2: GOOGLE ACCESS TOKEN EXISTS
    // ==============================
    if (googleToken) {
      try {
        // Token info from Google
        await axios.get(
          `https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=${googleToken}`
        );

        // Valid token → fetch user
        const user = await this.prisma.user.findUnique({
          where: { email: googleEmail },
        });

        if (!user) throw new Error("User not found");

        // Mark user as active in Redis (15 minutes TTL)
        // This is used by the cron job to only refresh tokens for online users
        const activeUserKey = `user_active:${user.id}`;
        const {success,error}= await safeSet(activeUserKey, '1', 900); // 15 minutes TTL
        if(!success){
          console.log("Error marking user as active:", error);
        }

        req.user = user;
        return true;
      } catch (e) {
        console.log("Google token expired → trying refresh...");

        // ==============================
        // TRY GOOGLE REFRESH TOKEN
        // ==============================

        if (!googleEmail) {
          res.clearCookie("google_access");
          if (isApiRequest) {
            throw new UnauthorizedException('Invalid or expired token');
          }
          res.redirect(`${process.env.FRONTEND_URL}/login`);
          return false;
        }

        const user = await this.prisma.user.findUnique({
          where: { email: googleEmail },
          include: {
            oauthProviders: {
              where: { provider: "google" },
            },
          },
        });

        const provider = user?.oauthProviders?.[0];
        if (!provider?.refreshToken) {
          res.clearCookie("google_access");
          if (isApiRequest) {
            throw new UnauthorizedException('Invalid or expired token');
          }
          res.redirect(`${process.env.FRONTEND_URL}/login`);
          return false;
        }

        // ==============================
        // Generate fresh access token from Google
        // ==============================
        try {
          const refreshRes = await axios.post(
            "https://oauth2.googleapis.com/token",
            {
              client_id: process.env.GOOGLE_CLIENT_ID,
              client_secret: process.env.GOOGLE_CLIENT_SECRET,
              refresh_token: provider.refreshToken,
              grant_type: "refresh_token",
            }
          );

          const newAccessToken = refreshRes.data.access_token;

          // Update cookie
          res.cookie("google_access", newAccessToken, {
            httpOnly: true,
            sameSite: "lax",
            secure: process.env.NODE_ENV === "production",
            maxAge: 2 * 60 * 60 * 1000,
          });

          // Mark user as active in Redis (15 minutes TTL)
          // This is used by the cron job to only refresh tokens for online users
          if (user) {
            const activeUserKey = `user_active:${user.id}`;
            const {success,error}= await safeSet(activeUserKey, '1', 900); // 5 minutes TTL
            if(!success){
              console.log("Error marking user as active:", error);
            }
          }

          if (!user) {
            res.clearCookie("google_access");
            res.clearCookie("google_user_email");
            if (isApiRequest) {
              throw new UnauthorizedException('User not found');
            }
            res.redirect(`${process.env.FRONTEND_URL}/login`);
            return false;
          }

          req.user = user;
          return true;
        } catch (refreshErr) {
          console.log("Google refresh failed:", refreshErr.message);

          // clear cookies
          res.clearCookie("google_access");
          res.clearCookie("google_user_email");
          if (isApiRequest) {
            throw new UnauthorizedException('Invalid or expired token');
          }
          res.redirect(`${process.env.FRONTEND_URL}/login`);
          return false;
        }
      }
    }

    // No token → redirect or throw
    if (isApiRequest) {
      throw new UnauthorizedException('Authentication required');
    }
    res.redirect(`${process.env.FRONTEND_URL}/login`);
    return false;
  }
}


