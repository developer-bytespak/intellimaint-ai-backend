import { Injectable, Logger } from '@nestjs/common';
import axios from 'axios';

export interface ImageData {
  base64: string;
  mimeType: string;
}

@Injectable()
export class ImageUtilService {
  private readonly logger = new Logger(ImageUtilService.name);

  /**
   * Download image from URL and convert to base64
   * Optimized for Vercel Blob URLs and other image sources
   * @param imageUrl - URL of the image to download (can be Vercel Blob URL, data URL, or external URL)
   * @returns Base64 encoded image data with MIME type, or null if download fails
   */
  async downloadImageAsBase64(imageUrl: string): Promise<ImageData | null> {
    try {
      // Handle data URLs (base64 already encoded)
      if (imageUrl.startsWith('data:')) {
        const [header, base64] = imageUrl.split(',');
        const mimeMatch = header.match(/data:([^;]+)/);
        const mimeType = mimeMatch ? mimeMatch[1] : 'image/jpeg';
        return {
          base64,
          mimeType,
        };
      }

      // Download image from URL (works for Vercel Blob URLs, external URLs, etc.)
      const response = await axios.get(imageUrl, {
        responseType: 'arraybuffer',
        timeout: 30000, // 30 second timeout
        maxContentLength: 10 * 1024 * 1024, // 10MB max
        // Vercel Blob URLs are public, no auth needed
        // For other URLs, add headers if needed
      });

      // Detect MIME type from response headers or URL
      let mimeType = response.headers['content-type'] || this.detectMimeTypeFromUrl(imageUrl);
      
      // Validate MIME type is an image
      if (!mimeType.startsWith('image/')) {
        mimeType = 'image/jpeg'; // Default fallback
      }

      // Convert to base64
      const base64 = Buffer.from(response.data).toString('base64');

      return {
        base64,
        mimeType,
      };
    } catch (error) {
      this.logger.error(`Failed to download image from ${imageUrl}:`, error.message);
      return null;
    }
  }

  /**
   * Detect MIME type from URL extension
   */
  private detectMimeTypeFromUrl(url: string): string {
    const extension = url.split('.').pop()?.toLowerCase() || '';
    const mimeTypes: Record<string, string> = {
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
      png: 'image/png',
      gif: 'image/gif',
      webp: 'image/webp',
      bmp: 'image/bmp',
      svg: 'image/svg+xml',
      heic: 'image/heic',
      heif: 'image/heif',
    };
    return mimeTypes[extension] || 'image/jpeg';
  }
}

