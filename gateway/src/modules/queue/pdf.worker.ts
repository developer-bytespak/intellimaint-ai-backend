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
  console.log("[worker] Redis connection:", redis);
  console.log("[worker] Queue name:", PDF_QUEUE_NAME);
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

      console.log(`[worker] ========================================`);
      console.log(`[worker] 🎯 PICKED JOB jobId=${jobId}`);
      console.log(`[worker] File: ${fileName}`);
      console.log(`[worker] Path: ${filePath}`);
      console.log(`[worker] Batch: ${batchId}`);
      console.log(`[worker] ========================================`);

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

        let startTime = Date.now();
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
        let elapsedTime = Date.now() - startTime;

        console.log(`[worker] ✅ Python response received after ${elapsedTime}ms`);
        console.log(`[worker] ✅ Response status: ${res.status}`);
        console.log(`[worker] Response data size: ${JSON.stringify(res.data).length} bytes`);
        
        // Don't log huge response data, just confirm it arrived
        if (res.data?.content) {
          console.log(`[worker] ✅ Content extracted: ${res.data.content.length} characters`);
        }

        // ⚠️ IMPORTANT: Don't include full content in Redis publish
        // The content is already saved in the database by Python
        // Including it here causes ECONNRESET on large documents
        // Just confirm extraction was successful

        // -----------------------------
        // STATUS → completed
        // Don't include content in Redis message (it's already in database)
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
          // ✅ Content is already saved in database by Python
          // ❌ Don't send it here to avoid ECONNRESET on large docs
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
      // ⚠️ CRITICAL: Extend lock duration for long-running extractions
      // Default is 30 seconds, but PDF extraction can take 1-5 minutes
      lockDuration: 1000 * 60 * 10, // 10 minutes - lock won't expire during extraction
      lockRenewTime: 1000 * 30, // Renew lock every 30 seconds
      // Prevent BullMQ from marking job as stalled
      stalledInterval: 1000 * 60 * 5, // Check for stalled jobs every 5 minutes
      maxStalledCount: 2, // Allow 2 stalls before failing
    }
  );

  worker.on("ready", () => {
    console.log("[worker] ✅ pdf worker ready - waiting for jobs");
    console.log(`[worker] Connected to queue: ${PDF_QUEUE_NAME}`);
    console.log(`[worker] Lock duration: 10 minutes`);
    console.log(`[worker] Lock renew time: 30 seconds`);
  });
  worker.on("error", (err) => console.error("[worker] ❌ worker error", err));
  worker.on("failed", (job, err) => {
    console.error(`[worker] ❌ failed jobId=${job?.data?.jobId}`);
    console.error(`[worker] Error: ${err.message}`);
  });
  worker.on("completed", (job) => {
    console.log(`[worker] ✅ Job completed: ${job?.data?.jobId}`);
  });
  // ⚠️ IMPORTANT: Log stalled jobs - this was causing the "failed" status
  worker.on("stalled", (jobId) => {
    console.error(`[worker] ⚠️ STALLED jobId=${jobId} - lock expired during long extraction`);
  });
}

async function publish(batchId: string, payload: any) {
  console.log(`[worker] 📢 Publishing to batch-events:${batchId}:`, payload); // 👈 ADD
  await redis.publish(
    `batch-events:${batchId}`,
    JSON.stringify({ ...payload, timestamp: Date.now() })
  );
}