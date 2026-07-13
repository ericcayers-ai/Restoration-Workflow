/*
 * Expandable per-stage job log (ROADMAP.md Phase 4.5.7).
 */

import { useState } from "react";
import { useT } from "../../lib/i18n";
import type { NodeEvent } from "../../lib/useJobEvents";
import styles from "./JobLogPanel.module.css";

export function JobLogPanel({
  events,
  open,
}: {
  events: Record<string, NodeEvent>;
  open: boolean;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  if (!open) return null;

  const rows = Object.entries(events).filter(([, e]) => e.status !== "queued");

  return (
    <div className={styles.panel}>
      <button
        type="button"
        className={styles.toggle}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {expanded ? t("simple.log.collapse") : t("simple.log.expand")}
      </button>
      {expanded && (
        <ul className={styles.list} aria-live="polite">
          {rows.length === 0 && <li className={styles.row}>{t("simple.log.waiting")}</li>}
          {rows.map(([nodeId, e]) => (
            <li key={nodeId} className={styles.row}>
              <span className="mono">{nodeId}</span>
              <span>{e.status}</span>
              {e.progress != null && (
                <span className="mono">{Math.round(e.progress * 100)}%</span>
              )}
              {e.message && <span className={styles.message}>{e.message}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
