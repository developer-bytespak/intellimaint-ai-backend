import { Worker, Job } from "bullmq";
import axios from "axios";
import { redis } from "src/common/lib/redis";
import { PDF_QUEUE_NAME } from "./bullmq.service";

const PYTHON_BASE = process.env.PYTHON_BASE_URL || "http://localhost:8000";

export function startPdfWorker() {
  console.log("[worker] starting pdf worker");

  const worker = new Worker(
    PDF_QUEUE_NAME,
    async (job: Job) => {
      const { jobId, batchId, fileName, filePath, user } = job.data as {
        jobId: string;
        batchId: string;
        fileName: string;
        filePath: string;
        user?: any;
      };

      console.log(`[worker] picked jobId=${jobId} file=${fileName}`);

      try {
        // -----------------------------
        // STATUS → processing
        // -----------------------------
        await redis.hset(`job:${jobId}`, {
          status: "processing",
          progress: 10,
          error: "",
        });

        await publish(batchId, {
          type: "job_updated",
          jobId,
          status: "processing",
          progress: 10,

        });

        // -----------------------------
        // CALL PYTHON EXTRACTION
        // -----------------------------
        console.log(`[worker] calling python extract jobId=${jobId}`);

        const res = await axios.post(
          `${PYTHON_BASE}/api/v1/extract/internal/run`,
          {
            batchId,
            jobId,
            fileName,
            filePath,
            user,
          },
          { timeout: 1000 * 60 * 30 } // 30 mins
        );

        // Python returns { ok:true }
        console.log(`[worker] python done jobId=${jobId}`, res.data);

        // -----------------------------
        // STATUS → completed
        // -----------------------------
        await redis.hset(`job:${jobId}`, {
          status: "completed",
          progress: 100,
          error: "",
        });

        await publish(batchId, {
          type: "job_updated",
          jobId,
          status: "completed",
          progress: 100,
          content: res.data.content,
        });

        console.log(`[worker] completed jobId=${jobId}`);
      } catch (err: any) {
        const msg = err?.response?.data?.detail || err.message || "Worker failed";

        console.error(`[worker] error jobId=${jobId}`, msg);

        await redis.hset(`job:${jobId}`, {
          status: "failed",
          error: msg,
          progress: 0,
        });

        await publish(batchId, {
          type: "job_updated",
          jobId,
          status: "failed",
          error: msg,
        });

        throw err; // let BullMQ retries happen
      }
    },
    {
      connection: redis,
      concurrency: 2,
    }
  );

  worker.on("ready", () => console.log("[worker] pdf worker ready"));
  worker.on("error", (err) => console.error("[worker] worker error", err));
  worker.on("failed", (job, err) =>
    console.error(`[worker] failed jobId=${job?.data?.jobId}`, err.message)
  );
}

async function publish(batchId: string, payload: any) {
  await redis.publish(
    `batch-events:${batchId}`,
    JSON.stringify({ ...payload, timestamp: Date.now() })
  );
}
