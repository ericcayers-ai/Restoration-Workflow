/*
 * "Center — Canvas. The DAG editor." (UI_DESIGN.md section 8). Keyboard
 * operability (section 6 — Tab between nodes, arrows nudge the selected one,
 * Enter to select) comes from React Flow's own built-in node a11y handling,
 * not a bespoke keydown hack here: each node div is natively focusable and
 * already answers Enter/Space/arrows before this component sees the event.
 * This component's own job is the drop-from-rail wiring, which needs the
 * canvas's screen<->flow coordinate mapping and so must live inside a
 * ReactFlowProvider it also renders.
 */

import { useCallback, type DragEvent } from "react";
import {
  Background,
  Controls,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import "../../styles/reactflow-theme.css";
import { useT } from "../../lib/i18n";
import { Button } from "../common/Button";
import { NodeCard } from "./NodeCard";
import type { RFEdge, RFNode } from "../../lib/canvasPipeline";
import styles from "./Canvas.module.css";

export const RAIL_DRAG_MIME = "application/x-restoration-node";

const NODE_TYPES = { restoration: NodeCard };

interface CanvasProps {
  nodes: RFNode[];
  edges: RFEdge[];
  onNodesChange: OnNodesChange<RFNode>;
  onEdgesChange: OnEdgesChange<RFEdge>;
  onConnect: OnConnect;
  onAddNodeAt: (nodeTypeId: string, position: { x: number; y: number }) => void;
  onRun: () => void;
  running: boolean;
  /** True when Run can't proceed for a reason other than "already running"
   *  or "no nodes yet" — Studio Mode passes `!file` here (no photo attached). */
  runDisabled?: boolean;
}

export function Canvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function CanvasInner({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onAddNodeAt,
  onRun,
  running,
  runDisabled = false,
}: CanvasProps) {
  const t = useT();
  const { screenToFlowPosition } = useReactFlow();

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const nodeTypeId = event.dataTransfer.getData(RAIL_DRAG_MIME);
      if (!nodeTypeId) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      onAddNodeAt(nodeTypeId, position);
    },
    [screenToFlowPosition, onAddNodeAt],
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  return (
    <div className={styles.wrap} onDrop={onDrop} onDragOver={onDragOver}>
      <ReactFlow<RFNode, RFEdge>
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={NODE_TYPES}
        fitView
        minZoom={0.2}
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
        <Panel position="top-right" className={styles.runPanel}>
          <Button
            variant="primary"
            icon="play"
            onClick={onRun}
            disabled={running || nodes.length === 0 || runDisabled}
          >
            {running ? t("studio.canvas.running") : t("studio.canvas.run")}
          </Button>
        </Panel>
        {nodes.length === 0 && (
          <Panel position="top-center">
            <p className={styles.emptyHint}>{t("studio.canvas.empty")}</p>
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}
