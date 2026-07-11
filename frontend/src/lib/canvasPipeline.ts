/*
 * Translates between the backend's PipelineJson (a plain DAG: nodes + edges,
 * ARCHITECTURE.md section 3) and React Flow's Node/Edge model, in both
 * directions — "Open in Studio" loads a real pipeline onto the canvas
 * (ROADMAP.md Phase 3), and "Run" turns whatever is on the canvas back into
 * the same JSON the executor already accepts.
 *
 * Two named-input node types exist today (`lama` needs a `mask`, `blend`
 * needs an `image_b`); every other node has exactly one input, `image`.
 * A future third-party plugin node with its own named inputs would need a
 * "+ input" affordance on the node card to generalize this — a real gap,
 * left as a Phase 6 follow-up rather than speculatively built now.
 */

import type { Edge, Node } from "@xyflow/react";
import type { DescribedNode, EdgeSpecJson, NodeCategory, NodeSpecJson, PipelineJson } from "./types";

export interface RestorationNodeData extends Record<string, unknown> {
  nodeType: string;
  displayName: string;
  category: NodeCategory;
  params: Record<string, unknown>;
  pinned: boolean;
  // Populated live from the job WebSocket while a run is in progress
  // (StudioMode syncs these onto the matching node id) — not part of the
  // pipeline JSON itself, so flowToPipeline never reads them.
  runStatus?: "queued" | "loading_weights" | "running" | "done" | "error";
  runProgress?: number;
  previewUrl?: string | null;
  cached?: boolean;
}

export type RFNode = Node<RestorationNodeData>;
export type RFEdge = Edge;

export const PRIMARY_HANDLE = "image";
export const SOURCE_HANDLE = "out";

const EXTRA_TARGET_HANDLES: Record<string, string[]> = {
  lama: ["mask"],
  blend: ["image_b"],
};

export function targetHandlesFor(nodeType: string): string[] {
  return [PRIMARY_HANDLE, ...(EXTRA_TARGET_HANDLES[nodeType] ?? [])];
}

const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 150;

/** Longest-path depth from any source node — purely for initial layout, not
 *  semantics; a cycle can't occur in a pipeline the backend already validated. */
function computeDepths(nodes: NodeSpecJson[], edges: EdgeSpecJson[]): Record<string, number> {
  const incoming: Record<string, string[]> = {};
  for (const n of nodes) incoming[n.id] = [];
  for (const e of edges) incoming[e.to]?.push(e.from);

  const depth: Record<string, number> = {};
  const visiting = new Set<string>();

  function computeDepth(id: string): number {
    if (id in depth) return depth[id]!;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const preds = incoming[id] ?? [];
    const d = preds.length === 0 ? 0 : 1 + Math.max(...preds.map(computeDepth));
    visiting.delete(id);
    depth[id] = d;
    return d;
  }

  for (const n of nodes) computeDepth(n.id);
  return depth;
}

function layoutPositions(pipeline: PipelineJson): Record<string, { x: number; y: number }> {
  const depths = computeDepths(pipeline.nodes, pipeline.edges);
  const byDepth: Record<number, string[]> = {};
  for (const n of pipeline.nodes) {
    const d = depths[n.id] ?? 0;
    (byDepth[d] ??= []).push(n.id);
  }
  const position: Record<string, { x: number; y: number }> = {};
  for (const [depthStr, ids] of Object.entries(byDepth)) {
    const depth = Number(depthStr);
    ids.forEach((id, row) => {
      position[id] = { x: depth * COLUMN_WIDTH, y: row * ROW_HEIGHT };
    });
  }
  return position;
}

export function pipelineToFlow(
  pipeline: PipelineJson,
  describedByType: Record<string, DescribedNode>,
): { nodes: RFNode[]; edges: RFEdge[] } {
  const positions = layoutPositions(pipeline);

  const nodes: RFNode[] = pipeline.nodes.map((n) => {
    const described = describedByType[n.type];
    return {
      id: n.id,
      type: "restoration",
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: {
        nodeType: n.type,
        displayName: described?.display_name ?? n.type,
        category: described?.category ?? "orchestration",
        params: n.params,
        pinned: n.pinned,
      },
    };
  });

  const edges: RFEdge[] = pipeline.edges.map((e) => ({
    id: `${e.from}->${e.to}:${e.to_input}`,
    source: e.from,
    target: e.to,
    sourceHandle: SOURCE_HANDLE,
    targetHandle: e.to_input,
  }));

  return { nodes, edges };
}

export function flowToPipeline(nodes: RFNode[], edges: RFEdge[]): PipelineJson {
  return {
    version: 1,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data.nodeType,
      params: n.data.params,
      pinned: n.data.pinned,
    })),
    edges: edges.map((e) => ({
      from: e.source,
      to: e.target,
      to_input: e.targetHandle ?? PRIMARY_HANDLE,
    })),
  };
}

let nodeCounter = 0;

export function createNode(
  described: DescribedNode,
  position: { x: number; y: number },
): RFNode {
  nodeCounter += 1;
  const defaults: Record<string, unknown> = {};
  for (const [key, spec] of Object.entries(described.param_schema.properties)) {
    if ("default" in spec) defaults[key] = spec.default;
  }
  return {
    id: `${described.id}_${nodeCounter}_${Date.now().toString(36)}`,
    type: "restoration",
    position,
    data: {
      nodeType: described.id,
      displayName: described.display_name,
      category: described.category,
      params: defaults,
      pinned: false,
    },
  };
}

/** A pipeline's single sink node — the one with no outgoing edge — mirrors
 *  the backend's own rule (executor.py sink_nodes) for which node's output
 *  is "the result." */
export function sinkNodeId(nodes: RFNode[], edges: RFEdge[]): string | null {
  const hasOutgoing = new Set(edges.map((e) => e.source));
  const sinks = nodes.filter((n) => !hasOutgoing.has(n.id));
  return sinks.length === 1 ? sinks[0]!.id : null;
}
