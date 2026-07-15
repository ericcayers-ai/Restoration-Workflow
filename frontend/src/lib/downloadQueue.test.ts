import { describe, expect, it } from "vitest";
import { createSerialQueue, runDownloadQueue } from "./downloadQueue";

describe("download queue", () => {
  it("serializes concurrent enqueue calls", async () => {
    const enqueue = createSerialQueue();
    const order: string[] = [];
    const slow = (label: string, ms: number) =>
      enqueue(async () => {
        order.push(`start:${label}`);
        await new Promise((r) => setTimeout(r, ms));
        order.push(`end:${label}`);
        return label;
      });

    const [a, b, c] = await Promise.all([slow("a", 30), slow("b", 5), slow("c", 1)]);
    expect([a, b, c]).toEqual(["a", "b", "c"]);
    expect(order).toEqual(["start:a", "end:a", "start:b", "end:b", "start:c", "end:c"]);
  });

  it("runDownloadQueue is sequential and cancel-aware", async () => {
    const seen: string[] = [];
    let cancel = false;
    const results = await runDownloadQueue(
      ["x", "y", "z"],
      async (id) => {
        seen.push(id);
        if (id === "y") cancel = true;
        return { state: "done" as const };
      },
      () => cancel,
    );
    expect(seen).toEqual(["x", "y"]);
    expect(results).toHaveLength(2);
  });

  it("continues after a prior enqueue rejection", async () => {
    const enqueue = createSerialQueue();
    await expect(
      enqueue(async () => {
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");
    await expect(enqueue(async () => "ok")).resolves.toBe("ok");
  });
});
