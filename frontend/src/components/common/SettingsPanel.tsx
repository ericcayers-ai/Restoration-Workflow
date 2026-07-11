/*
 * App settings, reached from the top bar. One tab today — Manage Downloads,
 * every model in the full stack in one place with its install state, size
 * and a download/remove control — structured so a second settings tab is a
 * sibling section, not a rewrite.
 */

import { useEffect, useState } from "react";
import { ApiError, acknowledgeLicense, listNodes, listWeights, removeWeights } from "../../lib/api";
import { formatBytes, licenseAbbrev } from "../../lib/format";
import { useT } from "../../lib/i18n";
import type { DescribedNode } from "../../lib/types";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "./Button";
import { DownloadRow } from "./DownloadRow";
import { Icon } from "./Icon";
import styles from "./SettingsPanel.module.css";

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const [nodes, setNodes] = useState<DescribedNode[]>([]);
  const [cacheDir, setCacheDir] = useState("");
  const [banner, setBanner] = useState<string | null>(null);
  const downloads = useWeightDownloads();

  function refresh() {
    listNodes()
      .then(setNodes)
      .catch(() => {});
    listWeights()
      .then((w) => setCacheDir(w.cache_dir))
      .catch(() => {});
  }

  useEffect(() => {
    if (open) refresh();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!banner) return;
    const timer = setTimeout(() => setBanner(null), 3500);
    return () => clearTimeout(timer);
  }, [banner]);

  if (!open) return null;

  const installable = nodes.filter((n) => n.weight_manifest.length > 0);

  function onAcknowledge(node: DescribedNode) {
    acknowledgeLicense(node.id)
      .then(() => refresh())
      .catch((err) => setBanner(err instanceof ApiError ? err.message : String(err)));
  }

  function onDownload(node: DescribedNode) {
    void downloads.download(node.id).then((result) => {
      if (result.state === "done") refresh();
    });
  }

  function onRemove(node: DescribedNode) {
    removeWeights(node.id)
      .then(() => {
        setBanner(t("settings.downloads.removed", { name: node.display_name }));
        refresh();
      })
      .catch((err) => setBanner(err instanceof ApiError ? err.message : String(err)));
  }

  return (
    <div
      className={styles.overlay}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={styles.panel} role="dialog" aria-modal="true" aria-label={t("settings.title")}>
        <header className={styles.header}>
          <h2>{t("settings.title")}</h2>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label={t("common.close")}>
            <Icon name="close" size={16} />
          </button>
        </header>

        <div className={styles.tabs}>
          <span className={styles.tabActive}>{t("settings.tab.downloads")}</span>
        </div>

        <div className={styles.body}>
          <p className={styles.subtitle}>{t("settings.downloads.subtitle")}</p>
          {cacheDir && (
            <p className={styles.cacheDir}>{t("settings.downloads.cacheDir", { path: cacheDir })}</p>
          )}
          {banner && <p className={styles.banner}>{banner}</p>}

          <ul className={styles.list}>
            {installable.map((node) => {
              const download = downloads.tracker[node.id];
              const needsAck = node.license.requires_acknowledgement && !node.weights.acknowledged;
              const installed = node.weights.installed;
              return (
                <li key={node.id} className={styles.row}>
                  <div className={styles.rowHeader}>
                    <span className={styles.name}>{node.display_name}</span>
                    <span className={styles.meta}>
                      {node.license.requires_acknowledgement && (
                        <span className={styles.licenseBadge} title={node.license.spdx_id}>
                          {licenseAbbrev(node.license.kind)}
                        </span>
                      )}
                      <span className="mono">{formatBytes(node.weights.total_size_bytes)}</span>
                    </span>
                  </div>

                  {needsAck ? (
                    <div className={styles.gate}>
                      <p>{t("studio.inspector.licenseGate.body")}</p>
                      <Button variant="danger" size="small" onClick={() => onAcknowledge(node)}>
                        {t("studio.inspector.licenseGate.accept")}
                      </Button>
                    </div>
                  ) : download && download.state === "running" ? (
                    <DownloadRow nodeId={node.id} download={download} />
                  ) : installed ? (
                    <div className={styles.installedRow}>
                      <span className={styles.installedLabel}>
                        <Icon name="check" size={12} />
                        {t("settings.downloads.installed", {
                          size: formatBytes(node.weights.total_size_bytes),
                        })}
                      </span>
                      <Button variant="ghost" size="small" icon="trash" onClick={() => onRemove(node)}>
                        {t("settings.downloads.remove")}
                      </Button>
                    </div>
                  ) : (
                    <Button variant="secondary" size="small" icon="tray" onClick={() => onDownload(node)}>
                      {t("settings.downloads.download", {
                        size: formatBytes(node.weights.total_size_bytes),
                      })}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
