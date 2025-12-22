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

    console.log(
      `[queue] enqueue request batchId=${batchId} jobId=${jobId} file=${fileName}`
    );

    await pdfQueue.add(
      "pdf-job",
      { batchId, jobId, fileName, filePath, user },
      { jobId } // IMPORTANT: keep jobId stable
    );

    return { ok: true, queued: true, jobId };
  }
}
