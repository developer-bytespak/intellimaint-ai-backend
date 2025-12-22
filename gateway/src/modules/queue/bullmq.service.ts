import { Queue } from "bullmq";
import { redis } from "src/common/lib/redis";

export const PDF_QUEUE_NAME = "pdf-jobs";

export const pdfQueue = new Queue(PDF_QUEUE_NAME, {
  connection: redis,
  defaultJobOptions: {
    attempts: 3,
    backoff: { type: "exponential", delay: 2000 },
    removeOnComplete: true,
    removeOnFail: false,
  },
});

export async function initQueues() {
  console.log("[bullmq] queue initializing...");
  // small ping to ensure queue is usable
  await pdfQueue.waitUntilReady();
  console.log("[bullmq] queue initialized");
}
