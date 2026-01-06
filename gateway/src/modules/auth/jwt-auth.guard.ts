import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import axios from 'axios';
import { Response } from 'express';
import * as jwt from 'jsonwebtoken';
import { PrismaService } from 'prisma/prisma.service';
import { appConfig } from 'src/config/app.config';
import { safeGet, redisDeleteKey, safeSet } from 'src/common/lib/redis';


@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(private prisma: PrismaService) { }

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const res: Response = context.switchToHttp().getResponse();

    const googleToken = req.cookies?.google_accessToken;
    const localToken = req.cookies?.local_accessToken;
    
    // CROSS-DOMAIN FIX: Check Authorization header for Bearer token
    // This is necessary when frontend and backend are on different domains
    // and cookies can't be shared cross-domain
    const authHeader = req.headers.authorization;
    const bearerToken = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : null;

    // Check if this is an API request (not a browser redirect)
    const isApiRequest =
      req.headers.accept?.includes('application/json') || req.path.startsWith('/api/');

    // ==============================
    // CASE 0: BEARER TOKEN (Authorization header) - for cross-domain auth
    // ==============================
    if (bearerToken) {
      try {
        const data = jwt.verify(bearerToken, appConfig.jwtSecret as string) as any;

        const user = await this.prisma.user.findUnique({
          where: { id: data.userId },
        });

        if (!user) throw new Error("User not found");

        req.user = user;
        return true;
      } catch (e) {
        console.log("Bearer token invalid or expired");
        if (isApiRequest) {
          throw new UnauthorizedException('Invalid or expired token');
        }
        return false;
      }
    }

    // ==============================
    // CASE 1: LOCAL TOKEN (cookie)
    // ==============================
    if (localToken) {
      try {
        const data = jwt.verify(localToken, appConfig.jwtSecret as string) as any;

        const user = await this.prisma.user.findUnique({
          where: { id: data.userId },
        });
        // console.log("user ==>", user);

        if (!user) throw new Error("User not found");

        req.user = user;
        return true;
      } catch (e) {
        res.clearCookie("local_accessToken");
        if (isApiRequest) {
          throw new UnauthorizedException('Invalid or expired token');
        }
        return false;
      }
    }

    // ==============================
    // CASE 2: GOOGLE ACCESS TOKEN EXISTS (cookie)
    // ==============================
    if (googleToken) {
      try {

        const decodeGoogleToken = jwt.verify(googleToken,appConfig.jwtSecret as string) as any;
        const userId = decodeGoogleToken?.userId;

        // Valid token → fetch user
        const user = await this.prisma.user.findUnique({
          where: { id: userId },
        });

        if (!user) throw new Error("User not found");

        req.user = user;
        return true;
      } catch (e) {
        console.log("Google token expired → trying refresh...");
          res.clearCookie("google_accessToken");
          if (isApiRequest) {
            throw new UnauthorizedException('Invalid or expired token');
          }
          return false;
        }
      }

    // No token → redirect or throw
   throw new UnauthorizedException('Authentication required');
  }
}


