/*
 * DAG pipeline canvas (ROADMAP.md Phase 3) — branch/merge editing without
 * re-introducing the full React Flow dependency removed in 0.2.0. Nodes are
 * keyboard-addressable cards; arrow keys nudge, Delete removes, Enter connects.
 * Incoming connections pick a port (image | image_b | mask) for blend / inpaint.
 */

import { useCallback, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import type { DagEdge, DagNode } from "../../lib/pipelineDag";
import styles from "./PipelineCanvas.module.css";

const NUDGE = 12;
const PORTS = ["image", "image_b", "mask"] as const;
type Port = (typeof PORTS)[number];

function defaultPortFor(nodeType: string): Port {
  if (nodeType === "blend") return "image_b";
  if (nodeType === "lama" || nodeType === "powerpaint" || nodeType === "flux_fill") return "mask";
  return "image";
}

export function PipelineCanvas({
  nodes,
  edges,
  selectedId,
  onSelect,
  onMoveNode,
  onConnect,
  onRemoveNode,
}: {
  nodes: DagNode[];
  edges: DagEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveNode: (id: string, x: number, y: number) => void;
  onConnect: (from: string, to: string, toInput: string) => void;
  onRemoveNode: (id: string) => void;
}) {
  const t = useT();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [connectFrom, setConnectFrom] = useState<string | null>(null);
  const [portPicker, setPortPicker] = useState<{ toId: string; x: number; y: number } | null>(
    null,
  );
  const [drag, setDrag] = useState<{ id: string; ox: number; oy: number } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent, node: DagNode) => {
      if ((e.target as HTMLElement).closest("button")) return;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      setDrag({ id: node.id, ox: e.clientX - rect.left - node.x, oy: e.clientY - rect.top - node.y });
      onSelect(node.id);
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [onSelect],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!drag || !canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      onMoveNode(drag.id, e.clientX - rect.left - drag.ox, e.clientY - rect.top - drag.oy);
    },
    [drag, onMoveNode],
  );

  const onPointerUp = useCallback(() => setDrag(null), []);

  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));

  function beginConnectTo(node: DagNode, clientX: number, clientY: number) {
    if (!connectFrom || connectFrom === node.id) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    setPortPicker({
      toId: node.id,
      x: clientX - (rect?.left ?? 0),
      y: clientY - (rect?.top ?? 0),
    });
  }

  function completeConnect(port: Port) {
    if (!connectFrom || !portPicker) return;
    onConnect(connectFrom, portPicker.toId, port);
    setConnectFrom(null);
    setPortPicker(null);
  }

  function onCanvasKeyDown(e: React.KeyboardEvent) {
    if (!selectedId) return;
    const node = nodeById[selectedId];
    if (!node) return;
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      onRemoveNode(selectedId);
      setConnectFrom(null);
      setPortPicker(null);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (connectFrom && connectFrom !== selectedId) {
        onConnect(connectFrom, selectedId, defaultPortFor(node.nodeType));
        setConnectFrom(null);
        setPortPicker(null);
      } else {
        setConnectFrom(selectedId);
      }
      return;
    }
    let dx = 0;
    let dy = 0;
    if (e.key === "ArrowLeft") dx = -NUDGE;
    else if (e.key === "ArrowRight") dx = NUDGE;
    else if (e.key === "ArrowUp") dy = -NUDGE;
    else if (e.key === "ArrowDown") dy = NUDGE;
    if (dx || dy) {
      e.preventDefault();
      onMoveNode(selectedId, node.x + dx, node.y + dy);
    }
  }

  return (
    <div
      ref={canvasRef}
      className={styles.canvas}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onClick={() => {
        onSelect(null);
        setPortPicker(null);
      }}
      onKeyDown={onCanvasKeyDown}
      role="application"
      aria-label={t("studio.canvas.dagLabel")}
      tabIndex={0}
    >
      <p className="visually-hidden">{t("studio.canvas.moveHint")}</p>
      <svg className={styles.edges} aria-hidden>
        {edges.map((e) => {
          const a = nodeById[e.from];
          const b = nodeById[e.to];
          if (!a || !b) return null;
          const x1 = a.x + 180;
          const y1 = a.y + 40;
          const x2 = b.x;
          const y2 = b.y + 40;
          const mx = (x1 + x2) / 2;
          return (
            <path
              key={e.id}
              className={styles.edge}
              d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
            />
          );
        })}
      </svg>

      {nodes.map((node) => (
        <div
          key={node.id}
          className={`${styles.node} ${selectedId === node.id ? styles.nodeSelected : ""}`}
          style={{ left: node.x, top: node.y }}
          onPointerDown={(e) => onPointerDown(e, node)}
          onClick={(e) => e.stopPropagation()}
          role="button"
          tabIndex={0}
          aria-label={t("studio.canvas.nodeStatus", {
            name: node.displayName,
            status: selectedId === node.id ? "selected" : "idle",
          })}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect(node.id);
            }
          }}
        >
          <span className={`${styles.tab} ${styles[`cat_${node.category}`] ?? ""}`} aria-hidden />
          <span className={`mono ${styles.nodeName}`}>{node.displayName}</span>
          <div className={styles.nodeActions}>
            <button
              type="button"
              className={styles.port}
              title={t("studio.canvas.connectOut")}
              aria-label={t("studio.canvas.connectOut")}
              onClick={(e) => {
                e.stopPropagation();
                setPortPicker(null);
                setConnectFrom(connectFrom === node.id ? null : node.id);
              }}
            >
              →
            </button>
            <button
              type="button"
              className={styles.port}
              title={t("studio.canvas.connectIn")}
              aria-label={t("studio.canvas.connectIn")}
              onClick={(e) => {
                e.stopPropagation();
                if (connectFrom && connectFrom !== node.id) {
                  beginConnectTo(node, e.clientX, e.clientY);
                }
              }}
            >
              ←
            </button>
            <button
              type="button"
              className={styles.delete}
              aria-label={t("studio.canvas.deleteNode")}
              onClick={(e) => {
                e.stopPropagation();
                onRemoveNode(node.id);
              }}
            >
              ×
            </button>
          </div>
        </div>
      ))}

      {portPicker && (
        <div
          className={styles.portMenu}
          style={{ left: portPicker.x, top: portPicker.y }}
          role="menu"
          aria-label={t("studio.canvas.portPicker")}
          onClick={(e) => e.stopPropagation()}
        >
          <p className={styles.portMenuTitle}>{t("studio.canvas.portPicker")}</p>
          {PORTS.map((port) => (
            <button
              key={port}
              type="button"
              role="menuitem"
              className={styles.portMenuItem}
              onClick={() => completeConnect(port)}
            >
              {t(`studio.canvas.port.${port}`)}
            </button>
          ))}
        </div>
      )}

      {nodes.length === 0 && <p className={styles.empty}>{t("studio.canvas.empty")}</p>}
      {connectFrom && !portPicker && <p className={styles.hint}>{t("studio.canvas.addEdgeHint")}</p>}
    </div>
  );
}
