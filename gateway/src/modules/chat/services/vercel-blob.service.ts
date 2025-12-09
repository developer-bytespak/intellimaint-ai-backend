import { Injectable, Logger } from '@nestjs/common';
import { put } from '@vercel/blob';
import { appConfig } from '../../../config/app.config';
import * as path from 'path';

@Injectable()
export class VercelBlobService {
  private readonly logger = new Logger(VercelBlobService.name);

  /**
   * Upload image buffer to Vercel Blob storage
   * @param buffer - Image buffer
   * @param originalName - Original filename
   * @returns Blob URL
   */
  async uploadImage(buffer: Buffer, originalName: string): Promise<string> {
    if (!appConfig.token) {
      this.logger.warn('Vercel Blob token is not configured. Skipping upload.');
      throw new Error('Vercel Blob token is not configured. Please set BLOB_READ_WRITE_TOKEN.');
    }

    try {
      const fileExtension = path.extname(originalName) || '.jpg';
      const uniqueFilename = `chat-images/${Date.now()}-${Math.random()
        .toString(36)
        .substring(7)}${fileExtension}`;

      const blob = await put(uniqueFilename, buffer, {
        access: 'public',
        addRandomSuffix: true,
        token: appConfig.token,
      });

      return blob.url;
    } catch (error) {
      this.logger.error('Error uploading image to Vercel Blob:', error);
      throw new Error(`Failed to upload image: ${error.message}`);
    }
  }

  /**
   * Upload base64 image to Vercel Blob storage
   * @param base64 - Base64 encoded image
   * @param mimeType - MIME type of the image
   * @returns Blob URL
   */
  async uploadBase64Image(base64: string, mimeType: string = 'image/jpeg'): Promise<string> {
    // Remove data URL prefix if present
    const cleanBase64 = base64.includes(',') ? base64.split(',')[1] : base64;
    
    // Convert base64 to buffer
    const buffer = Buffer.from(cleanBase64, 'base64');
    
    // Determine file extension from MIME type
    const extension = this.getExtensionFromMimeType(mimeType);
    const filename = `image${extension}`;
    
    return this.uploadImage(buffer, filename);
  }

  /**
   * Get file extension from MIME type
   */
  private getExtensionFromMimeType(mimeType: string): string {
    const mimeToExt: Record<string, string> = {
      'image/jpeg': '.jpg',
      'image/jpg': '.jpg',
      'image/png': '.png',
      'image/gif': '.gif',
      'image/webp': '.webp',
      'image/bmp': '.bmp',
      'image/svg+xml': '.svg',
      'image/heic': '.heic',
      'image/heif': '.heif',
    };
    return mimeToExt[mimeType] || '.jpg';
  }
}

