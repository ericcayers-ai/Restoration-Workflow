import { formatBytes } from "../../lib/format";
import { useT } from "../../lib/i18n";
import type { Download } from "../../lib/types";
import { Button } from "./Button";
import styles from "./DownloadRow.module.css";

export function DownloadRow({
  nodeId,
  displayName,
  download,
  onCancel,
}: {
  nodeId: string;
  displayName?: string;
  download?: Download;
  onCancel?: () => void;
}) {
  const t = useT();
  const percent = download ? Math.round(download.progress * 100) : 0;
  const fillClass = !download
    ? styles.fill
    : download.state === "error" || download.state === "cancelled"
      ? styles.fillError
      : download.state === "done"
        ? styles.fillDone
        : styles.fill;

  const statusText =
    download?.state === "error"
      ? download.error
      : download?.state === "cancelled"
        ? t("settings.downloads.cancelled")
        : download
          ? `${formatBytes(download.bytes_done)} / ${formatBytes(download.bytes_total)} (${percent}%)`
          : "…";

  return (
    <div className={styles.row} role="status" aria-live="polite">
      <div className={styles.label}>
        <span>{displayName ?? nodeId}</span>
        <span>{statusText}</span>
      </div>
      <div className={styles.track}>
        <div
          className={`${styles.fill} ${fillClass}`}
          style={{ transform: `scaleX(${Math.max(0, Math.min(1, percent / 100))})` }}
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={displayName ?? nodeId}
        />
      </div>
      {onCancel && download?.state === "running" && (
        <Button variant="ghost" size="small" onClick={onCancel}>
          {t("settings.downloads.cancel")}
        </Button>
      )}
    </div>
  );
}
