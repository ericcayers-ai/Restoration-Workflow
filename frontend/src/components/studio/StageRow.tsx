/*
 * One stage in the linear pipeline builder: a colored category tab, model
 * name in mono, a live thumbnail once it has run, a one-line parameter
 * summary, and reorder/remove controls — the same visual language the old
 * node-card canvas used (category color, cached badge, progress fill),
 * carried over to a plain ordered list instead of a graph.
 */

import type { CSSProperties } from "react";
import { Icon } from "../common/Icon";
import type { Stage } from "../../lib/pipelineStages";
import styles from "./StageRow.module.css";

function summarize(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return "defaults";
  return entries.map(([k, v]) => `${k}=${String(v)}`).join(" · ");
}

export function StageRow({
  stage,
  index,
  count,
  selected,
  onSelect,
  onMoveUp,
  onMoveDown,
  onRemove,
}: {
  stage: Stage;
  index: number;
  count: number;
  selected: boolean;
  onSelect: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}) {
  return (
    <li
      className={`${styles.row} ${selected ? styles.rowSelected : ""}`}
      data-status={stage.runStatus ?? "idle"}
      style={{ "--category-color": `var(--category-${stage.category})` } as CSSProperties}
    >
      <span className={styles.step}>{index + 1}</span>

      <button
        type="button"
        className={styles.main}
        onClick={onSelect}
        aria-pressed={selected}
        aria-label={`${stage.displayName} stage${stage.runStatus ? `, ${stage.runStatus}` : ""}`}
      >
        {stage.previewUrl && <img className={styles.thumb} src={stage.previewUrl} alt="" />}
        <div className={styles.textCol}>
          <span className={styles.name}>{stage.displayName}</span>
          <span className={styles.summary}>
            {summarize(stage.params)}
            {stage.cached && <span className={styles.badge}> · cached</span>}
          </span>
        </div>
        {(stage.runStatus === "running" || stage.runStatus === "loading_weights") && (
          <div className={styles.progressTrack}>
            <div
              className={styles.progressFill}
              style={{ width: `${Math.round((stage.runProgress ?? 0) * 100)}%` }}
            />
          </div>
        )}
      </button>

      <div className={styles.controls}>
        <button
          type="button"
          className={styles.iconButton}
          onClick={onMoveUp}
          disabled={index === 0}
          aria-label={`Move ${stage.displayName} earlier`}
        >
          <Icon name="arrow-up" size={13} />
        </button>
        <button
          type="button"
          className={styles.iconButton}
          onClick={onMoveDown}
          disabled={index === count - 1}
          aria-label={`Move ${stage.displayName} later`}
        >
          <Icon name="arrow-down" size={13} />
        </button>
        <button
          type="button"
          className={styles.iconButton}
          onClick={onRemove}
          aria-label={`Remove ${stage.displayName}`}
        >
          <Icon name="trash" size={13} />
        </button>
      </div>
    </li>
  );
}
