/*
 * Drives weight downloads and polls their progress. Shared between Simple
 * Mode's first-run auto-bootstrap, Studio Mode's per-node Inspector download
 * button, and Settings' manage-downloads queue.
 *
 * The backend has no download-progress WebSocket (only jobs do), so this
 * polls GET /api/weights/downloads/{id}. Downloads run sequentially so a
 * bulk "Download all" does not stampede the cache directory.
 */

import { useCallback, useRef, useState } from "react";
import { ApiError, cancelDownload, getDownload, startDownload, type StartDownloadOptions } from "./api";
import { createSerialQueue, runDownloadQueue } from "./downloadQueue";
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

function cancelledDownload(nodeId: string, id = ""): Download {
  const now = Date.now() / 1000;
  return {
    id,
    node_id: nodeId,
    state: "cancelled",
    filename: null,
    bytes_done: 0,
    bytes_total: 0,
    progress: 0,
    error: "cancelled",
    started_at: now,
    finished_at: now,
  };
}

export function useWeightDownloads() {
  const [tracker, setTracker] = useState<Record<string, Download>>({});
  const cancelledRef = useRef(false);
  const activeIdsRef = useRef<Map<string, string>>(new Map());
  const enqueueRef = useRef(createSerialQueue());

  const download = useCallback(
    async (nodeId: string, options: StartDownloadOptions = {}): Promise<Download> => {
      const run = async (): Promise<Download> => {
        try {
          let current = await startDownload(nodeId, options);
          activeIdsRef.current.set(nodeId, current.id);
          setTracker((prev) => ({ ...prev, [nodeId]: current }));
          while (current.state === "running" && !cancelledRef.current) {
            await sleep(POLL_INTERVAL_MS);
            current = await getDownload(current.id);
            setTracker((prev) => ({ ...prev, [nodeId]: current }));
          }
          if (cancelledRef.current && current.state === "running") {
            try {
              await cancelDownload(current.id);
              current = await getDownload(current.id);
            } catch {
              current = cancelledDownload(nodeId, current.id);
            }
            setTracker((prev) => ({ ...prev, [nodeId]: current }));
          }
          activeIdsRef.current.delete(nodeId);
          return current;
        } catch (err) {
          activeIdsRef.current.delete(nodeId);
          const message = err instanceof ApiError ? err.message : String(err);
          const errored = erroredDownload(nodeId, message);
          setTracker((prev) => ({ ...prev, [nodeId]: errored }));
          return errored;
        }
      };

      return enqueueRef.current(run);
    },
    [],
  );

  const downloadAll = useCallback(
    async (nodeIds: string[], options: StartDownloadOptions = {}): Promise<boolean> => {
      cancelledRef.current = false;
      const results = await runDownloadQueue(
        nodeIds,
        (id) => download(id, options),
        () => cancelledRef.current,
      );
      return results.length > 0 && results.every((r) => r.state === "done");
    },
    [download],
  );

  const cancel = useCallback(async (nodeId?: string) => {
    cancelledRef.current = true;
    const targets = nodeId
      ? [[nodeId, activeIdsRef.current.get(nodeId)] as const]
      : Array.from(activeIdsRef.current.entries());
    for (const [nid, downloadId] of targets) {
      if (!downloadId) continue;
      try {
        await cancelDownload(downloadId);
        const current = await getDownload(downloadId);
        setTracker((prev) => ({ ...prev, [nid]: current }));
      } catch {
        setTracker((prev) => ({ ...prev, [nid]: cancelledDownload(nid, downloadId) }));
      }
    }
  }, []);

  const reset = useCallback(() => {
    cancelledRef.current = false;
    activeIdsRef.current.clear();
    setTracker({});
  }, []);

  return { tracker, download, downloadAll, cancel, reset };
}
