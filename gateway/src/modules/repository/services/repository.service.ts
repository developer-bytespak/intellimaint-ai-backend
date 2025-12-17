import { Injectable, NotFoundException, ForbiddenException, BadRequestException } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { del } from '@vercel/blob';
import { DocumentMetadataDto } from '../dto/create-document.dto';
import { ListDocumentsQueryDto } from '../dto/list-documents.dto';
import { RepositoryStatus } from '@prisma/client';
import { FileMetadataDto } from '../dto/upload-urls.dto';
import { appConfig } from 'src/config/app.config';

@Injectable()
export class RepositoryService {
  constructor(private prisma: PrismaService) {}

  async generateUploadUrls(userId: string, files: FileMetadataDto[]) {
    if (!appConfig.token) {
      throw new BadRequestException('Blob storage not configured');
    }

    // Generate unique filenames and return upload URLs
    // Vercel Blob doesn't support presigned URLs like S3, so we return URLs
    // that can be used with their client SDK or server-side upload endpoint
    const uploadUrls = files.map((file) => {
      const timestamp = Date.now();
      const randomSuffix = Math.random().toString(36).substring(7);
      const fileExtension = file.fileName.includes('.')
        ? file.fileName.substring(file.fileName.lastIndexOf('.'))
        : '';
      const uniqueFileName = `${userId}/${timestamp}-${randomSuffix}${fileExtension}`;

      return {
        fileName: file.fileName,
        uploadUrl: uniqueFileName, // This will be used as the pathname for Vercel Blob
        contentType: file.contentType,
        fileSize: file.fileSize,
      };
    });

    return uploadUrls;
  }

  async createDocuments(userId: string, documents: DocumentMetadataDto[]) {
    const createdDocuments = await Promise.all(
      documents.map(async (doc) => {
        return await this.prisma.repository.create({
          data: {
            userId,
            fileName: doc.fileName,
            fileUrl: doc.fileUrl,
            fileSize: doc.fileSize,
            status: RepositoryStatus.ready,
          },
        });
      })
    );

    return createdDocuments;
  }

  async listDocuments(userId: string, query: ListDocumentsQueryDto) {
    // Ensure page and limit are numbers (query params come as strings)
    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 10;
    const skip = (page - 1) * limit;

    const where: any = {
      userId, // Ensure users only see their own documents
    };

    if (query.status) {
      where.status = query.status;
    }

    const [documents, total] = await Promise.all([
      this.prisma.repository.findMany({
        where,
        skip,
        take: limit,
        orderBy: {
          uploadedAt: 'desc',
        },
      }),
      this.prisma.repository.count({ where }),
    ]);

    return {
      documents,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  async getDocumentById(userId: string, id: string) {
    const document = await this.prisma.repository.findUnique({
      where: { id },
    });

    if (!document) {
      throw new NotFoundException('Document not found');
    }

    // Verify ownership
    if (document.userId !== userId) {
      throw new ForbiddenException('You do not have access to this document');
    }

    return document;
  }

  async deleteDocument(userId: string, id: string) {
    // First verify ownership
    const document = await this.getDocumentById(userId, id);

    const blobToken = process.env.BLOB_READ_WRITE_TOKEN;
    if (!blobToken) {
      throw new BadRequestException('Blob storage not configured');
    }

    // Delete from Vercel Blob
    try {
      await del(document.fileUrl, { token: blobToken });
    } catch (error) {
      // Log error but continue with database deletion
      console.error('Error deleting from blob storage:', error);
    }

    // Delete from database
    await this.prisma.repository.delete({
      where: { id },
    });

    return { success: true, message: 'Document deleted successfully' };
  }
}

