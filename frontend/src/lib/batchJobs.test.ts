import { describe, expect, it, vi } from "vitest";
import { runBatchSequentially, waitForJobDone } from "./batchJobs";
import type { Job } from "./types";

function job(partial: Partial<Job> & Pick<Job, "id" | "state">): Job {
  return {
    created_at: 0,
    started_at: null,
    finished_at: null,
    error: null,
    fallback: null,
    analysis: null,
    pipeline: { version: 1, nodes: [], edges: [] },
    result_url: null,
    events_truncated: false,
    ...partial,
  };
}

describe("batch sequencing", () => {
  it("waitForJobDone polls until terminal", async () => {
    const states: Job["state"][] = ["queued", "running", "done"];
    let i = 0;
    const getJobFn = vi.fn(async () => job({ id: "j1", state: states[i++]! }));
    const cancelJobFn = vi.fn();
    const result = await waitForJobDone("j1", () => false, {
      pollMs: 1,
      getJobFn,
      cancelJobFn,
    });
    expect(result.state).toBe("done");
    expect(getJobFn).toHaveBeenCalledTimes(3);
    expect(cancelJobFn).not.toHaveBeenCalled();
  });

  it("waitForJobDone cancels while polling", async () => {
    let cancelled = false;
    const getJobFn = vi.fn(async () => {
      if (!cancelled) {
        cancelled = true;
        return job({ id: "j1", state: "running" });
      }
      return job({ id: "j1", state: "cancelled" });
    });
    const cancelJobFn = vi.fn(async () => ({ cancelled: true }));
    const result = await waitForJobDone("j1", () => cancelled, {
      pollMs: 1,
      getJobFn,
      cancelJobFn,
    });
    expect(result.state).toBe("cancelled");
    expect(cancelJobFn).toHaveBeenCalled();
  });

  it("runBatchSequentially stops on cancel", async () => {
    let finished = 0;
    const runOne = vi.fn(async () => {
      finished += 1;
      return "done" as const;
    });
    const result = await runBatchSequentially(
      ["a", "b", "c"],
      runOne,
      () => finished >= 1,
    );
    expect(result.stopped).toBe("cancelled");
    expect(result.completed).toBe(1);
    expect(runOne).toHaveBeenCalledTimes(1);
  });

  it("runBatchSequentially completes all files", async () => {
    const result = await runBatchSequentially(
      ["a", "b"],
      async () => "done",
      () => false,
    );
    expect(result).toEqual({ completed: 2, stopped: "done" });
  });
});
