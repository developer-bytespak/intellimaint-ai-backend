import { Injectable } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service'; 
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';

@Injectable()
export class UploadService {
  constructor(private prisma: PrismaService) {}

  async getUserImages(
    userId: string, 
    res: Response, 
    page: number = 1,
    limit: number = 20
  ) {
    try {
      const skip = (page - 1) * limit;
      
      // Get total count for pagination
      const totalImages = await this.prisma.messageAttachment.count({
        where: {
          attachmentType: 'image',
          message: {
            session: {
              userId: userId,
            },
          },
        },
      });
      
      // Get paginated images
      const images = await this.prisma.messageAttachment.findMany({
        where: {
          attachmentType: 'image',
          message: {
            session: {
              userId: userId,
            },
          },
        },
        select: {
          id: true,
          fileUrl: true,
          fileName: true,
          metadata: true,
          createdAt: true,
          message: {
            select: {
              sessionId: true,
              createdAt: true,
            },
          },
        },
        orderBy: {
          createdAt: 'desc',
        },
        skip: skip,
        take: limit,
      });
      
      const hasMore = skip + images.length < totalImages;
      
      // Format response
      const formattedImages = images.map((img) => ({
        id: img.id,
        fileUrl: img.fileUrl,
        fileName: img.fileName,
        createdAt: img.createdAt,
        size: (img.metadata as any)?.size || 0,
      }));
      
      return nestResponse(200, 'Images fetched successfully', {
        images: formattedImages,
        total: totalImages,
        page: page,
        limit: limit,
        hasMore: hasMore,
      })(res as any);
      
    } catch (error) {
      return nestError(500, 'Failed to fetch images')(res as any);
    }
  }

  
}
