import { describe, expect, it } from "vitest";
import { createDownloadCancelTracker } from "./downloadCancel";
import { createSerialQueue, runDownloadQueue } from "./downloadQueue";

describe("download cancel tracker", () => {
  it("clears sticky cancel when a node starts downloading again", () => {
    const tracker = createDownloadCancelTracker();
    tracker.cancelNode("a");
    expect(tracker.isCancelled("a")).toBe(true);
    tracker.clearForDownload("a");
    expect(tracker.isCancelled("a")).toBe(false);
  });

  it("per-node cancel does not abort unrelated nodes", () => {
    const tracker = createDownloadCancelTracker();
    tracker.cancelNode("a");
    expect(tracker.isCancelled("a")).toBe(true);
    expect(tracker.isCancelled("b")).toBe(false);
    expect(tracker.isCancelAll()).toBe(false);
  });

  it("cancel-all aborts every node until cleared", () => {
    const tracker = createDownloadCancelTracker();
    tracker.cancelAllDownloads();
    expect(tracker.isCancelled("a")).toBe(true);
    expect(tracker.isCancelled("b")).toBe(true);
    expect(tracker.isCancelAll()).toBe(true);
    tracker.clearForDownloadAll();
    expect(tracker.isCancelled("a")).toBe(false);
    expect(tracker.isCancelAll()).toBe(false);
  });
});

describe("download queue with per-node cancel", () => {
  it("continues the bulk queue after a single-node cancel", async () => {
    const cancel = createDownloadCancelTracker();
    const seen: string[] = [];
    const results = await runDownloadQueue(
      ["a", "b", "c"],
      async (id) => {
        seen.push(id);
        cancel.clearForDownload(id);
        if (id === "b") {
          cancel.cancelNode("b");
          return { state: "cancelled" as const };
        }
        return { state: "done" as const };
      },
      () => cancel.isCancelAll(),
    );
    expect(seen).toEqual(["a", "b", "c"]);
    expect(results.map((r) => r.state)).toEqual(["done", "cancelled", "done"]);
  });

  it("stops the bulk queue on cancel-all", async () => {
    const cancel = createDownloadCancelTracker();
    const seen: string[] = [];
    const results = await runDownloadQueue(
      ["a", "b", "c"],
      async (id) => {
        seen.push(id);
        if (id === "a") cancel.cancelAllDownloads();
        return { state: "cancelled" as const };
      },
      () => cancel.isCancelAll(),
    );
    expect(seen).toEqual(["a"]);
    expect(results).toHaveLength(1);
  });

  it("serial queue still runs after a cancelled enqueue", async () => {
    const enqueue = createSerialQueue();
    const cancel = createDownloadCancelTracker();
    cancel.cancelNode("x");
    await expect(
      enqueue(async () => {
        if (cancel.isCancelled("x")) return "cancelled";
        return "ok";
      }),
    ).resolves.toBe("cancelled");
    cancel.clearForDownload("x");
    await expect(
      enqueue(async () => {
        if (cancel.isCancelled("x")) return "cancelled";
        return "ok";
      }),
    ).resolves.toBe("ok");
  });
});
