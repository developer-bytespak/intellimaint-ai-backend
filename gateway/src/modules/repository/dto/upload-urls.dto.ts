import { IsString, IsNumber, IsArray, ValidateNested, IsNotEmpty, Min } from 'class-validator';
import { Type } from 'class-transformer';

export class FileMetadataDto {
  @IsString()
  @IsNotEmpty()
  fileName!: string;

  @IsNumber()
  @Min(1)
  fileSize!: number;

  @IsString()
  @IsNotEmpty()
  contentType!: string;
}

export class UploadUrlsRequestDto {
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => FileMetadataDto)
  files!: FileMetadataDto[];
}

