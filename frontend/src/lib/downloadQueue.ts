/*
 * Sequential download queue primitives — shared by useWeightDownloads so
 * Settings "Download all" never stampedes the cache directory, and so unit
 * tests can cover queue ordering without mounting React.
 */

/** Serialize async work onto a single-file chain (FIFO). */
export function createSerialQueue() {
  let tail: Promise<unknown> = Promise.resolve();

  return function enqueue<T>(fn: () => Promise<T>): Promise<T> {
    const run = tail.then(() => fn(), () => fn());
    tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  };
}

/** Run node downloads one-at-a-time until cancel or exhaustion. */
export async function runDownloadQueue<T extends { state: string }>(
  nodeIds: string[],
  downloadOne: (nodeId: string) => Promise<T>,
  isCancelled: () => boolean,
): Promise<T[]> {
  const results: T[] = [];
  for (const id of nodeIds) {
    if (isCancelled()) break;
    results.push(await downloadOne(id));
  }
  return results;
}
