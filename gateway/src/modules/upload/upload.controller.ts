import { Controller, Post, Res, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import * as multer from 'multer';
import * as path from 'path';
import { put } from '@vercel/blob';  // Import Vercel Blob 
import { appConfig } from 'src/config/app.config';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';
@Controller('upload')
export class UploadController {
  @Post('file')
  @UseInterceptors(
    FileInterceptor('file', {
      storage: multer.memoryStorage(), // Store file in memory as buffer
      limits: { fileSize: 10 * 1024 * 1024 }, // File size limit: 10MB
    }),
  )
  async uploadFile(@UploadedFile() file: Express.Multer.File, @Res({ passthrough: true }) res: Response) {
    console.log("file", file);
    if (!file) {
     return nestError(400, 'No file uploaded')(res as any);
    }

    const fileExtension = path.extname(file.originalname);
    const uniqueFilename = `${Date.now()}-${Math.random().toString(36).substring(7)}${fileExtension}`;

    try {
      console.log("appConfig.token", appConfig.token);
      // Upload to Vercel Blob
      if (!appConfig.token) {
        return nestError(500, 'Vercel Blob token is not configured. Please set BLOB_READ_WRITE_TOKEN or VERCEL_BLOB_API_KEY environment variable.')(res as any);
      }

      const blob = await put(uniqueFilename, file.buffer, {
        access: 'public',
        addRandomSuffix: true, // Ensure unique file name
        token: appConfig.token,
      });
      console.log("blob", blob);

      return nestResponse(200, 'File uploaded successfully', {
        url: blob.url,
        pathname: blob.url,
      })(res as any);
    } catch (error) {
      console.error('Error uploading file:', error);
      return nestError(500, 'Error uploading file', error.message)(res as any);
    }
  }

  
}
