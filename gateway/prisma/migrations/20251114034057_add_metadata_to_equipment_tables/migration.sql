-- Ensure pgvector extension exists (for shadow database compatibility)
CREATE EXTENSION IF NOT EXISTS vector;

-- AlterTable
ALTER TABLE "equipment_families" ADD COLUMN "metadata" JSONB;

-- AlterTable
ALTER TABLE "equipment_models" ADD COLUMN "metadata" JSONB;

