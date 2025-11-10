ALTER TABLE "knowledge_sources"
  ADD COLUMN "user_id" UUID;

ALTER TABLE "knowledge_sources"
  ADD CONSTRAINT "knowledge_sources_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "users"("id")
  ON DELETE SET NULL ON UPDATE CASCADE;

CREATE INDEX "knowledge_sources_user_id_idx"
  ON "knowledge_sources"("user_id");
