import { Worker, Job } from "bullmq";
import axios from "axios";
import { redis } from "src/common/lib/redis";
import { PDF_QUEUE_NAME } from "./bullmq.service";

const PYTHON_BASE = process.env.PYTHON_BASE_URL || "http://localhost:8000";

export function startPdfWorker() {
  console.log("[worker] ========================================");
  console.log("[worker] 🚀 Starting PDF Worker");
  console.log("[worker] PYTHON_BASE_URL env var:", process.env.PYTHON_BASE_URL);
  console.log("[worker] PYTHON_BASE resolved to:", PYTHON_BASE);
  console.log("[worker] ========================================");

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

      console.log(`[worker] 🎯 PICKED JOB jobId=${jobId} file=${fileName} user=${user}`); // 👈 ENHANCED

      const pythonUrl = `${PYTHON_BASE}/api/v1/extract/internal/run`;

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

        console.log(`[worker] ✅ Python response status: ${res.status}`);
        console.log(`[worker] ✅ Python response data:`, res.data);

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
        // Extract detailed error information
        let msg = "Unknown error";
        let details = "";

        if (err?.response?.status) {
          msg = `HTTP ${err.response.status}: ${err.response?.data?.detail || err.response?.statusText || "Request failed"}`;
          details = `Response data: ${JSON.stringify(err.response.data)}`;
        } else if (err?.code) {
          msg = `${err.code}: ${err.message}`;
          details = `Connection error - ${err.message}`;
        } else if (err?.message) {
          msg = err.message;
          details = err.toString();
        }

        console.error(`[worker] ❌ ERROR jobId=${jobId}:`);
        console.error(`[worker] URL: ${pythonUrl}`);
        console.error(`[worker] Error: ${msg}`);
        console.error(`[worker] Details: ${details}`);
        console.error(`[worker] Stack:`, err?.stack);

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