import { IsString, IsNumber, IsArray, ValidateNested, IsNotEmpty, Min } from 'class-validator';
import { Type } from 'class-transformer';

export class DocumentMetadataDto {
  @IsString()
  @IsNotEmpty()
  fileId!: string;

  @IsString()
  @IsNotEmpty()
  fileName!: string;

  @IsString()
  @IsNotEmpty()
  fileUrl!: string;

  @IsNumber()
  @Min(1)
  fileSize!: number;

  @IsString()
  @IsNotEmpty()
  blobPath!: string;
}

export class CreateDocumentsRequestDto {
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => DocumentMetadataDto)
  documents!: DocumentMetadataDto[];
}

