/*
 * Drives weight downloads and polls their progress. Shared between Simple
 * Mode's first-run auto-bootstrap, Studio Mode's per-node Inspector download
 * button, and Settings' manage-downloads queue via WeightDownloadsProvider.
 *
 * The backend has no download-progress WebSocket (only jobs do), so this
 * polls GET /api/weights/downloads/{id} and periodically reconciles against
 * GET /api/weights/downloads so every surface shares one tracker.
 *
 * Downloads run sequentially so a bulk "Download all" does not stampede the
 * cache directory.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  cancelDownload,
  getDownload,
  listDownloads,
  startDownload,
  type StartDownloadOptions,
} from "./api";
import { createDownloadCancelTracker } from "./downloadCancel";
import { createSerialQueue, runDownloadQueue } from "./downloadQueue";
import type { Download } from "./types";

const POLL_INTERVAL_MS = 400;
const LIST_SYNC_MS = 1500;

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

export interface WeightDownloadsApi {
  tracker: Record<string, Download>;
  download: (nodeId: string, options?: StartDownloadOptions) => Promise<Download>;
  downloadAll: (nodeIds: string[], options?: StartDownloadOptions) => Promise<boolean>;
  cancel: (nodeId?: string) => Promise<void>;
  reset: () => void;
}

const WeightDownloadsContext = createContext<WeightDownloadsApi | null>(null);

function useWeightDownloadsStore(): WeightDownloadsApi {
  const [tracker, setTracker] = useState<Record<string, Download>>({});
  const cancelTracker = useRef(createDownloadCancelTracker()).current;
  const activeIdsRef = useRef<Map<string, string>>(new Map());
  const enqueueRef = useRef(createSerialQueue());

  // Keep Settings / Simple / Studio in sync with server-side download state.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const rows = await listDownloads();
        if (cancelled || rows.length === 0) return;
        setTracker((prev) => {
          const next = { ...prev };
          for (const row of rows) {
            next[row.node_id] = row;
            if (row.state === "running") {
              activeIdsRef.current.set(row.node_id, row.id);
            } else if (activeIdsRef.current.get(row.node_id) === row.id) {
              activeIdsRef.current.delete(row.node_id);
            }
          }
          return next;
        });
      } catch {
        // Poll failures must not break the UI; the per-id loop is authoritative.
      }
    };
    void tick();
    const handle = window.setInterval(() => void tick(), LIST_SYNC_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, []);

  const download = useCallback(
    async (nodeId: string, options: StartDownloadOptions = {}): Promise<Download> => {
      const run = async (): Promise<Download> => {
        cancelTracker.clearForDownload(nodeId);
        try {
          let current = await startDownload(nodeId, options);
          activeIdsRef.current.set(nodeId, current.id);
          setTracker((prev) => ({ ...prev, [nodeId]: current }));
          while (current.state === "running" && !cancelTracker.isCancelled(nodeId)) {
            await sleep(POLL_INTERVAL_MS);
            current = await getDownload(current.id);
            setTracker((prev) => ({ ...prev, [nodeId]: current }));
          }
          if (cancelTracker.isCancelled(nodeId) && current.state === "running") {
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
    [cancelTracker],
  );

  const downloadAll = useCallback(
    async (nodeIds: string[], options: StartDownloadOptions = {}): Promise<boolean> => {
      cancelTracker.clearForDownloadAll();
      const results = await runDownloadQueue(
        nodeIds,
        (id) => download(id, options),
        () => cancelTracker.isCancelAll(),
      );
      return results.length > 0 && results.every((r) => r.state === "done");
    },
    [cancelTracker, download],
  );

  const cancel = useCallback(
    async (nodeId?: string) => {
      if (nodeId) {
        cancelTracker.cancelNode(nodeId);
      } else {
        cancelTracker.cancelAllDownloads();
      }
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
    },
    [cancelTracker],
  );

  const reset = useCallback(() => {
    cancelTracker.reset();
    activeIdsRef.current.clear();
    setTracker({});
  }, [cancelTracker]);

  return useMemo(
    () => ({ tracker, download, downloadAll, cancel, reset }),
    [tracker, download, downloadAll, cancel, reset],
  );
}

export function WeightDownloadsProvider({ children }: { children: ReactNode }) {
  const value = useWeightDownloadsStore();
  return (
    <WeightDownloadsContext.Provider value={value}>{children}</WeightDownloadsContext.Provider>
  );
}

export function useWeightDownloads(): WeightDownloadsApi {
  const ctx = useContext(WeightDownloadsContext);
  if (!ctx) {
    throw new Error("useWeightDownloads must be used within WeightDownloadsProvider");
  }
  return ctx;
}
