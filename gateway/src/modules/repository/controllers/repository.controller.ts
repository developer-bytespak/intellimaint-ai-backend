import {
  Controller,
  Post,
  Get,
  Delete,
  Body,
  Param,
  Query,
  Req,
  UseGuards,
  Res,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { RepositoryService } from '../services/repository.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';
import { CreateDocumentsRequestDto } from '../dto/create-document.dto';
import { ListDocumentsQueryDto } from '../dto/list-documents.dto';
import { nestResponse, nestError } from 'src/common/helpers/responseHelpers';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import type { Response } from 'express';
import { FileInterceptor } from '@nestjs/platform-express';

@Controller('repository')
@UseGuards(JwtAuthGuard)
export class RepositoryController {
  constructor(private readonly repositoryService: RepositoryService) {}

  @Post('documents')
  // @UseInterceptors(FileInterceptor('file'))
  async createDocuments(
    // @UploadedFile() file: Express.Multer.File,
    @Req() req: any,
    @Body() body: any,
    @Res() res: Response,
  ) {
    try {
      // console.log("req ==>", req);
      const userId = req.user.id;
      // console.log("body ==>", body);
      const createDto = plainToInstance(CreateDocumentsRequestDto, body);
      console.log("createDto ==>", createDto);
      // return
      const errors = await validate(createDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const documents = await this.repositoryService.createDocuments(userId, createDto.documents);

      return nestResponse(200, 'Documents created successfully', { documents })(res);
    } catch (error) {
      console.error('Error creating documents:', error);
      return nestError(500, 'Failed to create documents', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Get('documents')
  async listDocuments(
    @Req() req: any,
    @Query() query: ListDocumentsQueryDto,
    @Res() res: Response,
  ) {
    try {
      const userId = req.user.id;
      const result = await this.repositoryService.listDocuments(userId, query);

      // console.log("result ==>", result);

      return nestResponse(200, 'Documents retrieved successfully', result)(res);
    } catch (error) {
      console.error('Error listing documents:', error);
      return nestError(500, 'Failed to retrieve documents', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Get('documents/:id')
  async getDocument(
    @Req() req: any,
    @Param('id') id: string,
    @Res() res: Response,
  ) {
    try { 
      // console.log("id ==>", id);
      const userId = req.user.id;
      const document = await this.repositoryService.getDocumentById(userId, id);

      return nestResponse(200, 'Document retrieved successfully', document)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      console.error('Error retrieving document:', error);
      return nestError(500, 'Failed to retrieve document', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Delete('documents/:id')
  async deleteDocument(
    @Req() req: any,
    @Param('id') id: string,
    @Res() res: Response,
  ) {
    try {
      const userId = req.user.id;
      const result = await this.repositoryService.deleteDocument(userId, id);

      return nestResponse(200, result.message, result)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      console.error('Error deleting document:', error);
      return nestError(500, 'Failed to delete document', error.message || 'Internal server error')(
        res,
      );
    }
  }
}


