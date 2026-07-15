/*
 * Batch job helpers — Studio Mode waits for each job to reach a terminal
 * state before submitting the next file.
 */

import { cancelJob, getJob } from "./api";
import type { Job } from "./types";

export async function waitForJobDone(
  jobId: string,
  isCancelled: () => boolean,
  {
    pollMs = 300,
    getJobFn = getJob,
    cancelJobFn = cancelJob,
  }: {
    pollMs?: number;
    getJobFn?: (id: string) => Promise<Job>;
    cancelJobFn?: (id: string) => Promise<unknown>;
  } = {},
): Promise<Job> {
  while (true) {
    if (isCancelled()) {
      await cancelJobFn(jobId);
    }
    const updated = await getJobFn(jobId);
    if (updated.state === "done" || updated.state === "error" || updated.state === "cancelled") {
      return updated;
    }
    await new Promise((r) => setTimeout(r, pollMs));
  }
}

/** Submit+wait for each file in order; stop early when cancelled. */
export async function runBatchSequentially<TFile>(
  files: TFile[],
  runOne: (file: TFile, index: number) => Promise<"done" | "error" | "cancelled">,
  isCancelled: () => boolean,
): Promise<{ completed: number; stopped: "done" | "cancelled" | "error" }> {
  let completed = 0;
  for (let i = 0; i < files.length; i++) {
    if (isCancelled()) {
      return { completed, stopped: "cancelled" };
    }
    const outcome = await runOne(files[i]!, i);
    if (outcome === "error") {
      return { completed, stopped: "error" };
    }
    if (outcome === "cancelled") {
      return { completed, stopped: "cancelled" };
    }
    completed += 1;
    if (isCancelled()) {
      return { completed, stopped: "cancelled" };
    }
  }
  return { completed, stopped: "done" };
}
