import { formatBytes } from "../../lib/format";
import type { Download } from "../../lib/types";
import styles from "./DownloadRow.module.css";

export function DownloadRow({ nodeId, download }: { nodeId: string; download?: Download }) {
  const percent = download ? Math.round(download.progress * 100) : 0;
  const fillClass = !download
    ? styles.fill
    : download.state === "error"
      ? styles.fillError
      : download.state === "done"
        ? styles.fillDone
        : styles.fill;

  return (
    <div className={styles.row}>
      <div className={styles.label}>
        <span>{nodeId}</span>
        <span>
          {download?.state === "error"
            ? download.error
            : download
              ? `${formatBytes(download.bytes_done)} / ${formatBytes(download.bytes_total)} (${percent}%)`
              : "…"}
        </span>
      </div>
      <div className={styles.track}>
        <div className={`${styles.fill} ${fillClass}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
