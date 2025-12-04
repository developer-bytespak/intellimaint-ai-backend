import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { SettingsDto } from '../dto/settings.dto';

@Injectable()
export class SettingsService {
  constructor(private prisma: PrismaService) {}

  async getSettings(userId: string) {
    let settings = await this.prisma.userSettings.findUnique({
      where: { userId },
    });

    // If settings don't exist, create default settings
    if (!settings) {
      settings = await this.prisma.userSettings.create({
        data: {
          userId,
          emailNotifications: true,
          theme: 'light',
        },
      });
    }

    return settings;
  }

  async updateSettings(userId: string, dto: SettingsDto) {
    // Verify user exists
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
    });

    if (!user) {
      throw new NotFoundException('User not found');
    }

    // Upsert settings
    const settings = await this.prisma.userSettings.upsert({
      where: { userId },
      update: {
        ...(dto.emailNotifications !== undefined && { emailNotifications: dto.emailNotifications }),
        ...(dto.theme !== undefined && { theme: dto.theme }),
      },
      create: {
        userId,
        emailNotifications: dto.emailNotifications ?? true,
        theme: dto.theme ?? 'light',
      },
    });

    return settings;
  }
}
