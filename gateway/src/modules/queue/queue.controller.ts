import { Body, Controller, Post } from "@nestjs/common";
import { pdfQueue } from "./bullmq.service";

@Controller("internal/queue")
export class QueueController {
  @Post("pdf/enqueue")
  async enqueuePdfJob(
    @Body()
    body: {
      batchId: string;
      jobId: string;
      fileName: string;
      filePath: string;
      user?: { userId?: string; name?: string; role?: string; email?: string };
    }
  ) {
    const { batchId, jobId, fileName, filePath, user } = body;

    console.log(`[queue] ======================================`);
    console.log(
      `[queue] 📥 Enqueue request: batchId=${batchId} jobId=${jobId}`
    );
    console.log(`[queue] File: ${fileName}`);
    console.log(`[queue] Path: ${filePath}`);

    try {
      const job = await pdfQueue.add(
        "pdf-job",
        { batchId, jobId, fileName, filePath, user },
        { jobId } // IMPORTANT: keep jobId stable
      );

      console.log(`[queue] ✅ Job added to queue with ID: ${job.id}`);
      console.log(`[queue] ======================================`);

      return { ok: true, queued: true, jobId };
    } catch (err: any) {
      console.error(`[queue] ❌ Failed to enqueue: ${err.message}`);
      console.error(`[queue] ======================================`);
      throw err;
    }
  }

  @Post("pdf/cancel-batch")
  async cancelBatchJobs(
    @Body()
    body: {
      batchId: string;
      jobIds: string[];
    }
  ) {
    const { batchId, jobIds } = body;

    console.log(`[queue] 🧹 Cancel request for batchId=${batchId}, jobs=${jobIds.length}`);

    let cancelled = 0;
    let failed = 0;

    for (const jobId of jobIds) {
      try {
        // Try to get the job from queue
        const job = await pdfQueue.getJob(jobId);
        
        if (job) {
          const state = await job.getState();
          console.log(`[queue] Job ${jobId} state: ${state}`);
          
          // Only remove if not already completed
          if (state !== "completed") {
            await job.remove();
            console.log(`[queue] ✅ Removed job ${jobId}`);
            cancelled++;
          } else {
            console.log(`[queue] ⏭️ Job ${jobId} already completed, skipping`);
          }
        } else {
          console.log(`[queue] ⚠️ Job ${jobId} not found in queue`);
        }
      } catch (err: any) {
        console.error(`[queue] ❌ Failed to cancel job ${jobId}:`, err.message);
        failed++;
      }
    }

    console.log(`[queue] 🧹 Batch ${batchId} cleanup done: ${cancelled} cancelled, ${failed} failed`);

    return { 
      ok: true, 
      batchId, 
      cancelled, 
      failed,
      total: jobIds.length 
    };
  }
}
