/*
 * Per-node vs cancel-all flags for weight downloads.
 *
 * A sticky global boolean made "cancel one node" abort every subsequent
 * download; this tracker keeps those scopes separate and clears the flag for
 * a node when that node starts downloading again.
 */

export function createDownloadCancelTracker() {
  const cancelledNodes = new Set<string>();
  let cancelAll = false;

  return {
    /** Clear sticky cancel for this node so a fresh download can proceed. */
    clearForDownload(nodeId: string) {
      cancelledNodes.delete(nodeId);
    },

    /** Reset bulk-cancel state before Download all. */
    clearForDownloadAll() {
      cancelAll = false;
      cancelledNodes.clear();
    },

    cancelNode(nodeId: string) {
      cancelledNodes.add(nodeId);
    },

    cancelAllDownloads() {
      cancelAll = true;
    },

    isCancelled(nodeId: string): boolean {
      return cancelAll || cancelledNodes.has(nodeId);
    },

    isCancelAll(): boolean {
      return cancelAll;
    },

    reset() {
      cancelAll = false;
      cancelledNodes.clear();
    },
  };
}

export type DownloadCancelTracker = ReturnType<typeof createDownloadCancelTracker>;
