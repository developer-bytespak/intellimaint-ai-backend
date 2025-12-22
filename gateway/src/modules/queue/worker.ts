import { startPdfWorker } from "./pdf.worker";

export async function startWorkers() {
  console.log("[worker] initializing workers...");

  startPdfWorker();

  console.log("[worker] all workers started");
}
