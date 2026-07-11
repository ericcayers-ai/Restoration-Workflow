/*
 * Drives weight downloads and polls their progress. Shared between Simple
 * Mode's first-run auto-bootstrap (a pipeline's weights are missing, so
 * fetch them with no click required — ROADMAP.md Phase 2's "zero
 * configuration" promise has to cover the very first photo, not just steady
 * state) and Studio Mode's per-node Inspector download button.
 *
 * The backend has no download-progress WebSocket (only jobs do), so this
 * polls GET /api/weights/downloads/{id} — cheap and short-lived enough that
 * polling is the right tool, not a second streaming channel.
 */

import { useCallback, useRef, useState } from "react";
import { ApiError, getDownload, startDownload } from "./api";
import type { Download } from "./types";

const POLL_INTERVAL_MS = 400;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function erroredDownload(nodeId: string, message: string): Download {
  const now = Date.now() / 1000;
  return {
    id: "",
    node_id: nodeId,
    state: "error",
    filename: null,
    bytes_done: 0,
    bytes_total: 0,
    progress: 0,
    error: message,
    started_at: now,
    finished_at: now,
  };
}

export function useWeightDownloads() {
  const [tracker, setTracker] = useState<Record<string, Download>>({});
  const cancelledRef = useRef(false);

  const download = useCallback(async (nodeId: string): Promise<Download> => {
    try {
      let current = await startDownload(nodeId);
      setTracker((prev) => ({ ...prev, [nodeId]: current }));
      while (current.state === "running" && !cancelledRef.current) {
        await sleep(POLL_INTERVAL_MS);
        current = await getDownload(current.id);
        setTracker((prev) => ({ ...prev, [nodeId]: current }));
      }
      return current;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      const errored = erroredDownload(nodeId, message);
      setTracker((prev) => ({ ...prev, [nodeId]: errored }));
      return errored;
    }
  }, []);

  const downloadAll = useCallback(
    async (nodeIds: string[]): Promise<boolean> => {
      cancelledRef.current = false;
      const results = await Promise.all(nodeIds.map((id) => download(id)));
      return results.every((r) => r.state === "done");
    },
    [download],
  );

  const cancel = useCallback(() => {
    cancelledRef.current = true;
  }, []);

  const reset = useCallback(() => setTracker({}), []);

  return { tracker, download, downloadAll, cancel, reset };
}
