import { Injectable, BadRequestException, NotFoundException } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { UpdateProfileDto } from '../dto/update-profile.dto';
import { ChangePasswordDto } from '../dto/change-password.dto';
import { DeleteAccountDto } from '../dto/delete-account.dto';
import { hashPassword } from 'src/common/helpers/hashing';
import * as bcrypt from 'bcryptjs';
import { redisDeleteKey, safeGet, safeSet } from 'src/common/lib/redis';
import { generateOTP } from 'src/common/helpers/generateOtp';
import { sendEmailOTP } from 'src/common/lib/nodemailer';

@Injectable()
export class UsersService {
  constructor(private prisma: PrismaService) {}

  async getProfile(userId: string) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        email: true,
        firstName: true,
        lastName: true,
        company: true,
        role: true,
        profileImageUrl: true,
        emailVerified: true,
        passwordHash: true, // Include to determine account type
        createdAt: true,
        updatedAt: true,
        userSettings: {
          select: {
            emailNotifications: true,
            theme: true,
            createdAt: true,
            updatedAt: true,
          },
        },
      },
    });

    if (!user) {
      throw new NotFoundException('User not found');
    }

    // Add account type indicator (OAuth accounts don't have passwordHash)
    const { passwordHash, ...userWithoutPassword } = user;
    return {
      ...userWithoutPassword,
      hasPassword: !!passwordHash, // true for regular accounts, false for OAuth
    };
  }

  async updateProfile(userId: string, dto: UpdateProfileDto) {
    // Check if email is being updated and if it's already taken
    if (dto.email) {
      const existingUser = await this.prisma.user.findUnique({
        where: { email: dto.email },
      });

      if (existingUser && existingUser.id !== userId) {
        throw new BadRequestException('Email already in use');
      }
    }

    const updateData: any = {};
    if (dto.firstName !== undefined && dto.firstName !== null) updateData.firstName = dto.firstName;
    if (dto.lastName !== undefined && dto.lastName !== null) updateData.lastName = dto.lastName;
    if (dto.email !== undefined && dto.email !== null) updateData.email = dto.email;
    if (dto.profileImageUrl !== undefined && dto.profileImageUrl !== null) updateData.profileImageUrl = dto.profileImageUrl;
    if (dto.company !== undefined && dto.company !== null) updateData.company = dto.company;
    
    // If no data to update, return current user
    if (Object.keys(updateData).length === 0) {
      return this.getProfile(userId);
    }

    const updatedUser = await this.prisma.user.update({
      where: { id: userId },
      data: updateData,
      select: {
        id: true,
        email: true,
        firstName: true,
        lastName: true,
        company: true,
        role: true,
        profileImageUrl: true,
        emailVerified: true,
        createdAt: true,
        updatedAt: true,
      },
    });

    return updatedUser;
  }

  async changePassword(userId: string, dto: ChangePasswordDto) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      select: { id: true, passwordHash: true },
    });

    if (!user) {
      throw new NotFoundException('User not found');
    }

    if (!user.passwordHash) {
      throw new BadRequestException('Password cannot be changed for OAuth users');
    }

    // Verify current password
    const isPasswordValid = await bcrypt.compare(dto.currentPassword, user.passwordHash);
    if (!isPasswordValid) {
      throw new BadRequestException('Current password is incorrect');
    }

    // Hash new password
    const hashedPassword = await hashPassword(dto.newPassword);

    // Update password
    await this.prisma.user.update({
      where: { id: userId },
      data: { passwordHash: hashedPassword },
    });

    return { message: 'Password changed successfully' };
  }

  async deleteAccount(userId: string, dto?: DeleteAccountDto) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      select: { id: true, email: true, passwordHash: true },
    });

    if (!user) {
      throw new NotFoundException('User not found');
    }

    // If user has a password, require password verification
    if (user.passwordHash) {
      if (!dto?.password) {
        throw new BadRequestException('Password is required to delete account');
      }
      const isPasswordValid = await bcrypt.compare(dto.password, user.passwordHash);
      if (!isPasswordValid) {
        throw new BadRequestException('Password is incorrect');
      }
    } else {
      // OAuth user (no password) - require OTP verification
      if (!dto?.otp) {
        throw new BadRequestException('OTP is required to delete account. Please request OTP first.');
      }
      
      // Verify OTP
      const rediskey = `otp:delete_account:${user.email}`;
      const storedOtp = await safeGet(rediskey);
      
      if (!storedOtp) {
        throw new BadRequestException('OTP expired or not found. Please request a new OTP.');
      }
      
      if (storedOtp.toString() !== dto.otp.toString()) {
        throw new BadRequestException('Invalid OTP');
      }
      
      // OTP verified - delete the OTP from Redis
      await redisDeleteKey(rediskey);
    }

    // Hard delete: completely remove the user record from database
    // Related records will be cascade deleted automatically:
    // - OAuthProvider (onDelete: Cascade)
    // - OTP (onDelete: Cascade)
    // - Session (onDelete: Cascade)
    // - ChatSession (onDelete: Cascade) -> ChatMessage -> MessageAttachment
    // - Subscription (onDelete: Cascade)
    // - UserSettings (onDelete: Cascade)
    // - KnowledgeSource will have userId set to null (onDelete: SetNull)
    await this.prisma.user.delete({
      where: { id: userId },
    });

    // Clear Redis cache
    await redisDeleteKey(`user_active:${userId}`);

    return { message: 'Account deleted successfully' };
  }

  async sendDeleteAccountOtp(userId: string) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      select: { id: true, email: true, passwordHash: true },
    });

    if (!user) {
      throw new NotFoundException('User not found');
    }

    // Only send OTP for OAuth users (users without password)
    if (user.passwordHash) {
      throw new BadRequestException('OTP is not required. Please provide your password to delete account.');
    }

    // Generate and store OTP
    const rediskey = `otp:delete_account:${user.email}`;
    const otpCode = generateOTP();
    const { success, error } = await safeSet(rediskey, otpCode, 300); // 5 minutes

    if (!success) {
      throw new BadRequestException('Failed to generate OTP', error);
    }

    // Send OTP via email
    const result = await sendEmailOTP(user.email, otpCode);
    if (!result.success) {
      throw new BadRequestException('Failed to send OTP', result.message);
    }

    return { message: `OTP sent successfully to ${user.email}` };
  }

  // Keep existing methods for backward compatibility
  async findOne(id: string) {
    return this.getProfile(id);
  }

  async update(id: string, updateDto: any) {
    return this.updateProfile(id, updateDto);
  }
}
