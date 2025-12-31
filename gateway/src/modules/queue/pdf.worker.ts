import { Worker, Job } from "bullmq";
import axios from "axios";
import { redis } from "src/common/lib/redis";
import { PDF_QUEUE_NAME } from "./bullmq.service";

const PYTHON_BASE = process.env.PYTHON_BASE_URL || "http://localhost:8000";

export function startPdfWorker() {
  console.log("[worker] starting pdf worker");
  console.log(`[worker] PYTHON_BASE_URL = ${PYTHON_BASE}`); // 👈 ADD THIS

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

      console.log(`[worker] 🎯 PICKED JOB jobId=${jobId} file=${fileName}`); // 👈 ENHANCED

      try {
        // -----------------------------
        // STATUS → processing
        // -----------------------------
        console.log(`[worker] Setting status to processing for jobId=${jobId}`); // 👈 ADD
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

        await redis.hset(`job:${jobId}`, {
          status: "processing",
          progress: 30,
          error: "",
        });

        await publish(batchId, {
          type: "job_updated",
          jobId,
          status: "processing",
          progress: 30,
        });

        // -----------------------------
        // CALL PYTHON EXTRACTION
        // -----------------------------
        const pythonUrl = `http://localhost:8000/api/v1/extract/internal/run`;
        console.log(`[worker] 📡 Calling Python at: ${pythonUrl}`); // 👈 ADD
        console.log(`[worker] Payload:`, { jobId, batchId, fileName, filePath }); // 👈 ADD

        const res = await axios.post(
          pythonUrl,
          {
            batchId,
            jobId,
            fileName,
            filePath,
            user,
          },
          { timeout: 1000 * 60 * 30 } // 30 mins
        );

        console.log(`[worker] ✅ Python response:`, res.data); // 👈 ADD

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

        console.log(`[worker] ✅ COMPLETED jobId=${jobId}`);
      } catch (err: any) {
        const msg = err?.response?.data?.detail || err.message || "Worker failed";

        console.error(`[worker] ❌ ERROR jobId=${jobId}:`, msg);
        console.error(`[worker] Full error:`, err); // 👈 ADD FULL ERROR

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

  worker.on("ready", () => console.log("[worker] ✅ pdf worker ready"));
  worker.on("error", (err) => console.error("[worker] ❌ worker error", err));
  worker.on("failed", (job, err) =>
    console.error(`[worker] ❌ failed jobId=${job?.data?.jobId}`, err.message)
  );

  worker.on("completed", (job) =>
    console.log(`[worker] ✅ Job completed: ${job?.data?.jobId}`)
  ); // 👈 ADD THIS
}

async function publish(batchId: string, payload: any) {
  console.log(`[worker] 📢 Publishing to batch-events:${batchId}:`, payload); // 👈 ADD
  await redis.publish(
    `batch-events:${batchId}`,
    JSON.stringify({ ...payload, timestamp: Date.now() })
  );
}