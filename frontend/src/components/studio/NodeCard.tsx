/*
 * "Nodes are rectangular cards with a hairline border (no drop shadows),
 * a colored category tab on the left edge, model name in mono, a small live
 * thumbnail once the node has executed, and a one-line parameter summary."
 * (UI_DESIGN.md section 8)
 */

import type { CSSProperties } from "react";
import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { Icon } from "../common/Icon";
import { PRIMARY_HANDLE, SOURCE_HANDLE, targetHandlesFor, type RFNode } from "../../lib/canvasPipeline";
import styles from "./NodeCard.module.css";

function summarize(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return "defaults";
  return entries.map(([k, v]) => `${k}=${String(v)}`).join(" · ");
}

export function NodeCard({ id, data, selected }: NodeProps<RFNode>) {
  const { deleteElements } = useReactFlow();
  const handles = targetHandlesFor(data.nodeType);

  return (
    <div
      className={styles.card}
      data-status={data.runStatus ?? "idle"}
      style={{ "--category-color": `var(--category-${data.category})` } as CSSProperties}
      role="group"
      aria-label={`${data.displayName} node${data.runStatus ? `, ${data.runStatus}` : ""}`}
    >
      {handles.map((handleId, index) => (
        <Handle
          key={handleId}
          id={handleId}
          type="target"
          position={Position.Left}
          style={{ top: `${((index + 1) * 100) / (handles.length + 1)}%` }}
        />
      ))}

      <div className={styles.header}>
        <span className={styles.name}>{data.displayName}</span>
        <button
          type="button"
          className={styles.deleteButton}
          onClick={() => deleteElements({ nodes: [{ id }] })}
          aria-label={`Delete ${data.displayName}`}
          title="Delete node"
        >
          <Icon name="trash" size={13} />
        </button>
      </div>

      {data.previewUrl && <img className={styles.thumb} src={data.previewUrl} alt="" />}

      <p className={styles.summary}>
        {summarize(data.params)}
        {data.cached && <span className={styles.badge}> · cached</span>}
      </p>

      {(data.runStatus === "running" || data.runStatus === "loading_weights") && (
        <div className={styles.progressTrack}>
          <div
            className={styles.progressFill}
            style={{ width: `${Math.round((data.runProgress ?? 0) * 100)}%` }}
          />
        </div>
      )}

      <Handle id={SOURCE_HANDLE} type="source" position={Position.Right} />

      {selected && handles.length > 1 && (
        <div className={styles.handleLabel} style={{ left: -4, top: -14 }}>
          {handles.join(" / ")}
        </div>
      )}
    </div>
  );
}

export { PRIMARY_HANDLE };
