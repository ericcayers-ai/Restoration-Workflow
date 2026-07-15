/*
 * App settings, reached from the top bar. Manage Downloads lists every model
 * with install state, licence gates, totals, cancel controls, and Download all.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  acknowledgeLicense,
  cleanupJobs,
  listNodes,
  listWeights,
  removeWeights,
} from "../../lib/api";
import { downloadSizeBytes, formatBytes, licenseAbbrev, licenseBadgeHint } from "../../lib/format";
import { useT } from "../../lib/i18n";
import { useFocusTrap } from "../../lib/useFocusTrap";
import type { DescribedNode } from "../../lib/types";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "./Button";
import { DownloadRow } from "./DownloadRow";
import { Icon } from "./Icon";
import styles from "./SettingsPanel.module.css";

type Filter = "all" | "missing" | "installed" | "restricted";

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const panelRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<DescribedNode[]>([]);
  const [cacheDir, setCacheDir] = useState("");
  const [banner, setBanner] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [totals, setTotals] = useState<{
    missing_node_ids: string[];
    permissive: { count: number; bytes: number };
    restricted: { count: number; bytes: number };
    grand: { count: number; bytes: number };
  } | null>(null);
  const downloads = useWeightDownloads();

  useFocusTrap(open, panelRef, onClose);

  function refresh() {
    listNodes()
      .then(setNodes)
      .catch(() => {});
    listWeights()
      .then((w) => {
        setCacheDir(w.cache_dir);
        setTotals(w.totals ?? null);
      })
      .catch(() => {});
  }

  useEffect(() => {
    if (open) {
      setQuery("");
      setFilter("all");
      refresh();
    }
  }, [open]);

  useEffect(() => {
    if (!banner) return;
    const timer = setTimeout(() => setBanner(null), 3500);
    return () => clearTimeout(timer);
  }, [banner]);

  const installable = useMemo(() => nodes.filter((n) => n.weight_manifest.length > 0), [nodes]);

  const computedTotals = useMemo(() => {
    if (totals) return totals;
    let permissiveBytes = 0;
    let restrictedBytes = 0;
    let permissiveN = 0;
    let restrictedN = 0;
    const missing: string[] = [];
    for (const node of installable) {
      if (node.weights.installed) continue;
      missing.push(node.id);
      const size = downloadSizeBytes(node.weights);
      if (node.license.requires_acknowledgement) {
        restrictedBytes += size;
        restrictedN += 1;
      } else {
        permissiveBytes += size;
        permissiveN += 1;
      }
    }
    return {
      missing_node_ids: missing,
      permissive: { count: permissiveN, bytes: permissiveBytes },
      restricted: { count: restrictedN, bytes: restrictedBytes },
      grand: { count: permissiveN + restrictedN, bytes: permissiveBytes + restrictedBytes },
    };
  }, [totals, installable]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return installable.filter((node) => {
      if (needle) {
        const hay = `${node.display_name} ${node.id}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      if (filter === "missing") return !node.weights.installed;
      if (filter === "installed") return node.weights.installed;
      if (filter === "restricted") return node.license.requires_acknowledgement;
      return true;
    });
  }, [installable, query, filter]);

  const onAcknowledge = useCallback(
    (node: DescribedNode) => {
      acknowledgeLicense(node.id)
        .then(() => refresh())
        .catch((err) => setBanner(err instanceof ApiError ? err.message : String(err)));
    },
    [],
  );

  async function onAckAllRestricted() {
    const pending = installable.filter(
      (n) => n.license.requires_acknowledgement && !n.weights.acknowledged,
    );
    for (const node of pending) {
      try {
        await acknowledgeLicense(node.id);
      } catch (err) {
        setBanner(err instanceof ApiError ? err.message : String(err));
        return;
      }
    }
    refresh();
  }

  function onDownload(node: DescribedNode, allVariants = false) {
    void downloads.download(node.id, { all_variants: allVariants }).then((result) => {
      if (result.state === "done") refresh();
      if (result.state === "error") {
        setBanner(t("settings.downloads.failed", { error: result.error ?? "" }));
      }
    });
  }

  async function onDownloadAll() {
    const needAck = installable.filter(
      (n) =>
        !n.weights.installed &&
        n.license.requires_acknowledgement &&
        !n.weights.acknowledged,
    );
    if (needAck.length) {
      await onAckAllRestricted();
    }
    const missing = computedTotals.missing_node_ids.length
      ? computedTotals.missing_node_ids
      : installable.filter((n) => !n.weights.installed).map((n) => n.id);
    if (!missing.length) return;
    setBulkBusy(true);
    setBanner(t("settings.downloads.downloadingAll"));
    const ok = await downloads.downloadAll(missing);
    setBulkBusy(false);
    refresh();
    setBanner(ok ? t("settings.downloads.allDone") : t("simple.stage.error"));
  }

  function onRemove(node: DescribedNode) {
    removeWeights(node.id)
      .then(() => {
        setBanner(t("settings.downloads.removed", { name: node.display_name }));
        refresh();
      })
      .catch((err) => setBanner(err instanceof ApiError ? err.message : String(err)));
  }

  async function onCleanupJobs() {
    try {
      const result = await cleanupJobs();
      setBanner(t("settings.jobs.cleaned", { count: result.purged }));
    } catch (err) {
      setBanner(err instanceof ApiError ? err.message : String(err));
    }
  }

  if (!open) return null;

  return (
    <div
      className={styles.overlay}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label={t("settings.title")}
      >
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

          <div className={styles.bulkRow}>
            <p className={styles.totals}>
              {t("settings.downloads.totals", {
                permissive: `${computedTotals.permissive.count} (${formatBytes(computedTotals.permissive.bytes)})`,
                restricted: `${computedTotals.restricted.count} (${formatBytes(computedTotals.restricted.bytes)})`,
                grand: `${computedTotals.grand.count} (${formatBytes(computedTotals.grand.bytes)})`,
              })}
            </p>
            <div className={styles.bulkActions}>
              <Button
                variant="ghost"
                size="small"
                onClick={() => void onAckAllRestricted()}
                disabled={bulkBusy}
              >
                {t("settings.downloads.ackAll")}
              </Button>
              <Button
                variant="secondary"
                size="small"
                icon="tray"
                onClick={() => void onDownloadAll()}
                disabled={bulkBusy || computedTotals.grand.count === 0}
              >
                {t("settings.downloads.downloadAll")}
              </Button>
              {bulkBusy && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => void downloads.cancel()}
                >
                  {t("settings.downloads.cancelAll")}
                </Button>
              )}
              <Button variant="ghost" size="small" onClick={() => void onCleanupJobs()}>
                {t("settings.jobs.cleanup")}
              </Button>
            </div>
          </div>

          <div className={styles.filterRow}>
            <label className={styles.searchField}>
              <span className="visually-hidden">{t("settings.downloads.search")}</span>
              <Icon name="loupe" size={14} />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("settings.downloads.search")}
              />
            </label>
            <div className={styles.filterChips} role="radiogroup" aria-label={t("settings.downloads.filterAll")}>
              {(
                [
                  ["all", "settings.downloads.filterAll"],
                  ["missing", "settings.downloads.filterMissing"],
                  ["installed", "settings.downloads.filterInstalled"],
                  ["restricted", "settings.downloads.filterRestricted"],
                ] as const
              ).map(([value, key]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={filter === value}
                  className={filter === value ? styles.filterActive : styles.filterChip}
                  onClick={() => setFilter(value)}
                >
                  {t(key)}
                </button>
              ))}
            </div>
          </div>

          {banner && <p className={styles.banner} role="status">{banner}</p>}

          <ul className={styles.list}>
            {filtered.length === 0 && (
              <li className={styles.empty}>{t("settings.downloads.empty")}</li>
            )}
            {filtered.map((node) => {
              const download = downloads.tracker[node.id];
              const needsAck = node.license.requires_acknowledgement && !node.weights.acknowledged;
              const installed = node.weights.installed;
              const size = downloadSizeBytes(node.weights);
              return (
                <li key={node.id} className={styles.row}>
                  <div className={styles.rowHeader}>
                    <span className={styles.name}>{node.display_name}</span>
                    <span className={styles.meta}>
                      {node.license.requires_acknowledgement && (
                        <span
                          className={styles.licenseBadge}
                          title={licenseBadgeHint(node.license.kind) || node.license.spdx_id}
                        >
                          {licenseAbbrev(node.license.kind)}
                        </span>
                      )}
                      <span className="mono">{formatBytes(size)}</span>
                    </span>
                  </div>

                  {needsAck ? (
                    <div className={styles.gate}>
                      <p>{t("studio.inspector.licenseGate.body")}</p>
                      <Button variant="danger" size="small" onClick={() => onAcknowledge(node)}>
                        {t("studio.inspector.licenseGate.accept")}
                      </Button>
                    </div>
                  ) : download && (download.state === "running" || download.state === "error" || download.state === "cancelled") ? (
                    <DownloadRow
                      nodeId={node.id}
                      displayName={node.display_name}
                      download={download}
                      onCancel={() => void downloads.cancel(node.id)}
                    />
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
                    <div className={styles.downloadActions}>
                      <Button variant="secondary" size="small" icon="tray" onClick={() => onDownload(node)}>
                        {t("settings.downloads.download", { size: formatBytes(size) })}
                      </Button>
                      <Button
                        variant="ghost"
                        size="small"
                        onClick={() => onDownload(node, true)}
                      >
                        {t("settings.downloads.downloadAllVariants")}
                      </Button>
                    </div>
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
