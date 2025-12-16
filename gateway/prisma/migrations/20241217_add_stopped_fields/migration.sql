-- Add isStopped and stoppedAt fields to chat_messages table
ALTER TABLE "chat_messages" 
ADD COLUMN IF NOT EXISTS "is_stopped" BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS "stopped_at" TIMESTAMP(6);

-- Create index for faster queries on stopped messages
CREATE INDEX IF NOT EXISTS "chat_messages_is_stopped_idx" ON "chat_messages"("is_stopped") WHERE "is_stopped" = true;
