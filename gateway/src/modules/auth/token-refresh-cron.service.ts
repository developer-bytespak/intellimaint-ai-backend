  import { Injectable, Logger, UseGuards } from '@nestjs/common';
  import { Cron, CronExpression } from '@nestjs/schedule';
  import { PrismaService } from 'prisma/prisma.service';
  import * as jwt from 'jsonwebtoken';
  import { appConfig } from 'src/config/app.config';
  import { safeGet, safeSet } from 'src/common/lib/redis';


  @Injectable()
  export class TokenRefreshCronService {
    private readonly logger = new Logger(TokenRefreshCronService.name);

    constructor(private prisma: PrismaService) {}

    // Run every 5 minutes
    @Cron(CronExpression.EVERY_5_MINUTES)
    async handleTokenRefresh() {
      this.logger.log('Starting token refresh cron job...');

      try {
        const now = new Date();
        // Find sessions where 50+ minutes have passed since creation
        // We check sessions created 50 minutes ago or earlier
        const fiftyMinutesAgo = new Date(now.getTime() - 50 * 60 * 1000);

        // Get all active sessions that were created 50+ minutes ago and haven't expired
        const sessionsToRefresh = await this.prisma.session.findMany({
          where: {
            createdAt: {
              lte: fiftyMinutesAgo, // Created 50+ minutes ago
            },
            expiresAt: {
              gt: now, // Still not expired
            },
          },
          include: {
            user: true,
          },
        });

        this.logger.log(`Found ${sessionsToRefresh.length} sessions to refresh`);

        for (const session of sessionsToRefresh) {
          try {
            // Verify the user still exists and is verified
            if (!session.user || !session.user.emailVerified) {
              this.logger.warn(`Skipping session ${session.id} - user not verified`);
              continue;
            }

            // Check if user is active/online (only refresh tokens for online users)
            const activeUserKey = `user_active:${session.userId}`;
            const isUserActive = await safeGet(activeUserKey);
            console.log("isUserActive ==>");
            
            if (!isUserActive) {
              // User is offline, skip token refresh
              this.logger.log(`Skipping session ${session.id} - user ${session.userId} is offline`);
              continue;
            }

            // Check if we've already refreshed this session recently (within last 10 minutes)
            // to avoid refreshing multiple times
            const lastRefreshKey = `last_token_refresh:${session.id}`;
            const lastRefresh = await safeGet(lastRefreshKey);
            console.log("lastRefresh ==>", lastRefresh);
            if (lastRefresh) {
              // Skip if refreshed recently
              console.log("Skipping session ${session.id} - user ${session.userId} is offline");
              continue;
            }

            // Generate new access token (1 hour expiry)
            const newAccessToken = jwt.sign(
              { userId: session.userId },
              appConfig.jwtSecret as string,
              { expiresIn: '1h' }
            );
            // console.log("newAccessToken ==>", newAccessToken);

            // Generate new refresh token (7 days expiry)
            const newRefreshToken = jwt.sign(
              { userId: session.userId },
              appConfig.jwtSecret as string,
              { expiresIn: '7d' }
            );

            // Update session in DB with new refresh token and expiry
            await this.prisma.session.update({
              where: { id: session.id },
              data: {
                token: newRefreshToken,
                expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
              },
            });

            // Store new access token in Redis for the guard to pick up
            // Key format: pending_access_token:${userId}
            const redisKey = `pending_access_token:${session.userId}`;
            const {success,error}= await safeSet(redisKey, newAccessToken, 3600); // 1 hour TTL
            if(!success){
              console.log("Error storing new access token:", error);
            }

            // Mark that we've refreshed this session (expires in 10 minutes)
            const {success:success2,error:error2}= await safeSet(lastRefreshKey, '1', 600); // 10 minutes
            if(!success2){
              console.log("Error marking last refresh:", error2);
            }

            this.logger.log(`Refreshed tokens for user ${session.userId}`);
          } catch (error) {
            this.logger.error(
              `Error refreshing tokens for session ${session.id}:`,
              error
            );
          }
        }

        this.logger.log('Token refresh cron job completed');
      } catch (error) {
        this.logger.error('Error in token refresh cron job:', error);
      }
    }
  }

