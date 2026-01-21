/**
 * Pipeline Message DTO
 * 
 * This file defines the request and response types for the RAG chat pipeline API.
 * It includes validation decorators for input validation and type definitions
 * for internal communication between services.
 * 
 * Responsibilities:
 * - Define PipelineMessageDto (request from frontend)
 * - Define PipelineChunk (response chunk for streaming)
 * - Define helper types (ImageAnalysisResult, TokenUsage, etc.)
 * - Provide validation rules
 */

import { IsString, IsArray, IsOptional, MaxLength, ArrayMaxSize } from 'class-validator';

/**
 * Request DTO for pipeline message submission
 */
export class PipelineMessageDto {
  @IsString()
  @MaxLength(5000)
  content: string;

  @IsArray()
  @ArrayMaxSize(5)
  @IsOptional()
  images?: string[];
}

/**
 * Token usage tracking for cost management
 */
export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  cachedTokens?: number;
}

/**
 * Image analysis result from OpenAI Vision API
 */
export interface ImageAnalysisResult {
  attachmentId: string;
  description: string;
  detectedComponents?: Record<string, unknown>;
  ocrResults?: string;
  modelId?: string;
}

/**
 * Knowledge chunk for RAG context
 */
export interface KnowledgeChunkData {
  id: string;
  content: string;
  heading?: string;
  metadata?: Record<string, unknown>;
  tokenCount?: number;
  sourceId: string;
  chunkIndex?: number;
}

/**
 * Pipeline chunk - individual update streamed during processing
 */
export interface PipelineChunk {
  stage:
    | 'image-analysis'
    | 'embedding'
    | 'retrieval'
    | 'context'
    | 'llm-generation'
    | 'complete'
    | 'error';
  token?: string;
  metadata?: {
    analyses?: ImageAnalysisResult[];
    chunkCount?: number;
    retrievedChunks?: KnowledgeChunkData[];
    imageDescriptions?: string;
    tokenUsage?: TokenUsage;
  };
  messageId?: string;
  errorMessage?: string;
  done?: boolean;
}

/**
 * Context data prepared for LLM call
 */
export interface ContextData {
  summary: string;
  recentMessages: any[];
}
