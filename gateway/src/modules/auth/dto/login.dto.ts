import { UserRole } from '@prisma/client';
import { IsEmail, IsEnum, IsIn, IsOptional, IsString, MaxLength, MinLength } from 'class-validator';

export class LoginDto {
  @IsEmail()
  email: string;

  @IsString()
  password: string;
}
export class RegisterDto {
  @IsEmail({},{message: 'Invalid email address'})
  email: string;

  @IsString({message: 'Password must be a string'})
  @MinLength(8,{message: 'Password must be at least 8 characters long'})
  password: string;

  @IsString({message: 'Confirm password must be a string'})
  @MinLength(8,{message: 'Password must be at least 8 characters long'})
  confirmPassword: string;

  @IsEnum(UserRole,{message: 'Invalid role'})
  role: UserRole;

  @IsString({message: 'First name must be a string'})
  @IsOptional()
  firstName?: string;

  @IsString({message: 'Last name must be a string'})
  @IsOptional()
  lastName?: string;

  @IsString({message: 'Company must be a string'})
  @IsOptional()
  company?: string;
}

export class VerifyOtpDto{
  @IsEmail()
  email: string;

  @IsString()
  @MinLength(6)
  @MinLength(6)
  code: string; // 6 digit OTP
}

