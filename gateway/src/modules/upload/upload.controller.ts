// import { Controller, Post, Res, UploadedFile, UseInterceptors,Get } from '@nestjs/common';
// import { FileInterceptor } from '@nestjs/platform-express';
// import * as multer from 'multer';
// import * as path from 'path';
// import { put } from '@vercel/blob';  // Import Vercel Blob 
// import { appConfig } from 'src/config/app.config';
// import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';
// import { UploadService } from './upload.service';

// @Controller('upload')
// export class UploadController {
//   constructor(private readonly uploadService: UploadService) {}
//   @Post('file')
//   @UseInterceptors(
//     FileInterceptor('file', {
//       storage: multer.memoryStorage(), // Store file in memory as buffer
//       limits: { fileSize: 10 * 1024 * 1024 }, // File size limit: 10MB
//     }),
//   )
//   async uploadFile(@UploadedFile() file: Express.Multer.File, @Res() res: Response) {
//     console.log("file", file);
//     if (!file) {
//      return nestError(400, 'No file uploaded')(res as any);
//     }

//     const fileExtension = path.extname(file.originalname);
//     const uniqueFilename = `${Date.now()}-${Math.random().toString(36).substring(7)}${fileExtension}`;

//     try {
//       console.log("appConfig.token", appConfig.token);
//       // Upload to Vercel Blob
//       if (!appConfig.token) {
//         return nestError(500, 'Vercel Blob token is not configured. Please set BLOB_READ_WRITE_TOKEN or VERCEL_BLOB_API_KEY environment variable.')(res as any);
//       }

//       const blob = await put(uniqueFilename, file.buffer, {
//         access: 'public',
//         addRandomSuffix: true, // Ensure unique file name
//         token: appConfig.token,
//       });
//       console.log("blob", blob);

//       return nestResponse(200, 'File uploaded successfully', {
//         url: blob.url,
//         pathname: blob.url,
//       })(res as any);
//     } catch (error) {
//       console.error('Error uploading file:', error);
//       return nestError(500, 'Error uploading file', error.message)(res as any);
//     }
//   }

//   @Get('/history/images')
// async getHistoryImages(@Req() req) {
//   const userId = req.user.id; // assuming JWT auth
//   return this.uploadService.getUserImages(userId);
// }

// }


import {
  Controller,
  Post,
  Res,
  UploadedFile,
  UseInterceptors,
  Get,
  Req,
  Body,
  UseGuards,
  Query
} from '@nestjs/common';

import { FileInterceptor } from '@nestjs/platform-express';
import * as multer from 'multer';
import * as path from 'path';
import { put } from '@vercel/blob';
import { appConfig } from 'src/config/app.config';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';
import { UploadService } from './upload.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('upload')
export class UploadController {
  constructor(private readonly uploadService: UploadService) {}

  // Upload File
  @Post('file')
  @UseInterceptors(
    FileInterceptor('file', {
      storage: multer.memoryStorage(),
      limits: { fileSize: 10 * 1024 * 1024 }, // 10MB limit
    }),
  )
  async uploadFile(
    @UploadedFile() file: Express.Multer.File,
    @Res() res: Response
  ) {
    if (!file) return nestError(400, 'No file uploaded')(res as any);

    const fileExtension = path.extname(file.originalname);
    const uniqueFilename = `${Date.now()}-${Math.random()
      .toString(36)
      .substring(7)}${fileExtension}`;

    if (!appConfig.token) {
      return nestError(
        500,
        'Missing Vercel Blob token'
      )(res as any);
    }

    try {
      const blob = await put(uniqueFilename, file.buffer, {
        access: 'public',
        addRandomSuffix: true,
        token: appConfig.token,
      });

      return nestResponse(200, 'File uploaded successfully', {
        url: blob.url,
        pathname: blob.pathname,
      })(res as any);
    } catch (error:any) {
      console.error('Upload error:', error);
      return nestError(500, 'Error uploading file', error.message)(res as any);
    }
  }

  @UseGuards(JwtAuthGuard)
  @Get('/history/images')
  async getHistoryImages(
    @Req() req: Request, 
    @Res() res: Response,
    @Query('page') page?: number,        // ✅ Add this
    @Query('limit') limit?: number       // ✅ Add this
  ) {
    if(!(req as any).user){
      return nestError(401, 'Unauthorized')(res as any);
    }
    const userId = (req as Request & { user: { id: string } }).user.id;
    if (!userId) {
      return nestError(401, 'Unauthorized')(res as any);
    }
    
    // ✅ Pass pagination params to service
    const pageNumber = page ? parseInt(page.toString()) : 1;
    const pageSize = limit ? parseInt(limit.toString()) : 20; // Default 20
    
    return this.uploadService.getUserImages(userId, res, pageNumber, pageSize);
  }
}

