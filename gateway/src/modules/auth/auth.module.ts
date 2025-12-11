// import { Module } from '@nestjs/common';
// import { AuthController } from './auth.controller';
// import { AuthService } from './auth.service';
// import { JwtStrategy } from './jwt.strategy';

// @Module({
//   controllers: [AuthController],
//   providers: [AuthService, JwtStrategy],
//   exports: [AuthService],
// })
// export class AuthModule {}

import * as dotenv from 'dotenv';
dotenv.config();
import { Module } from '@nestjs/common';
import { PassportModule } from '@nestjs/passport';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import { GoogleStrategy } from './google.strategy'; 
import { PrismaService } from 'prisma/prisma.service';
import { JwtAuthGuard } from './jwt-auth.guard';
import { TokenRefreshCronService } from './token-refresh-cron.service';
console.log("googleStrategyEnabled");

const googleStrategyEnabled =
  process.env.GOOGLE_CLIENT_ID &&
  process.env.GOOGLE_CLIENT_SECRET &&
  process.env.GOOGLE_CALLBACK_URL;

@Module({
  imports: [PassportModule],
  controllers: [AuthController],
  providers: [
    AuthService,
    PrismaService,
    JwtAuthGuard,
    TokenRefreshCronService,
    ...(googleStrategyEnabled ? [GoogleStrategy] : []),
  ],
  exports: [JwtAuthGuard],
})
export class AuthModule {}
