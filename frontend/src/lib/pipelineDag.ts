/*
 * DAG pipeline editor state (ROADMAP.md Phase 3 branch/merge).
 * Complements the linear stage list — pipelines with blend nodes or multiple
 * branches are authored here and round-trip as PipelineJson.
 */

import type { DescribedNode, EdgeSpecJson, NodeSpecJson, PipelineJson } from "./types";

export interface DagNode {
  id: string;
  nodeType: string;
  displayName: string;
  category: DescribedNode["category"];
  params: Record<string, unknown>;
  pinned: boolean;
  x: number;
  y: number;
}

export interface DagEdge {
  id: string;
  from: string;
  to: string;
  toInput: string;
}

let idCounter = 0;

function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}_${idCounter}_${Date.now().toString(36)}`;
}

export function createDagNode(described: DescribedNode, x = 80, y = 80): DagNode {
  const defaults: Record<string, unknown> = {};
  for (const [key, spec] of Object.entries(described.param_schema.properties)) {
    if ("default" in spec) defaults[key] = spec.default;
  }
  return {
    id: nextId(described.id),
    nodeType: described.id,
    displayName: described.display_name,
    category: described.category,
    params: defaults,
    pinned: false,
    x,
    y,
  };
}

export function pipelineToDag(
  pipeline: PipelineJson,
  describedByType: Record<string, DescribedNode>,
): { nodes: DagNode[]; edges: DagEdge[] } {
  const nodes: DagNode[] = pipeline.nodes.map((n, i) => {
    const described = describedByType[n.type];
    return {
      id: n.id,
      nodeType: n.type,
      displayName: described?.display_name ?? n.type,
      category: described?.category ?? "orchestration",
      params: n.params,
      pinned: n.pinned ?? false,
      x: 80 + (i % 3) * 220,
      y: 80 + Math.floor(i / 3) * 140,
    };
  });
  const edges: DagEdge[] = pipeline.edges.map((e, i) => ({
    id: `e${i}`,
    from: e.from,
    to: e.to,
    toInput: e.to_input ?? "image",
  }));
  return { nodes, edges };
}

export function dagToPipeline(
  nodes: DagNode[],
  edges: DagEdge[],
): { pipeline: PipelineJson; error: string | null } {
  if (nodes.length === 0) {
    return { pipeline: { version: 1, nodes: [], edges: [] }, error: null };
  }
  const nodeIds = new Set(nodes.map((n) => n.id));
  for (const e of edges) {
    if (!nodeIds.has(e.from) || !nodeIds.has(e.to)) {
      return { pipeline: { version: 1, nodes: [], edges: [] }, error: "Edge references a missing node." };
    }
  }
  const pipelineNodes: NodeSpecJson[] = nodes.map((n) => ({
    id: n.id,
    type: n.nodeType,
    params: n.params,
    pinned: n.pinned,
  }));
  const pipelineEdges: EdgeSpecJson[] = edges.map((e) => ({
    from: e.from,
    to: e.to,
    to_input: e.toInput,
  }));
  return { pipeline: { version: 1, nodes: pipelineNodes, edges: pipelineEdges }, error: null };
}

/** Preset template: two face nodes on the same input, blended (Phase 3 acceptance). */
export function dualFaceBlendTemplate(
  describedByType: Record<string, DescribedNode>,
): { nodes: DagNode[]; edges: DagEdge[] } | null {
  const faceA = describedByType.osdface ?? describedByType.gfpgan;
  const faceB =
    describedByType.gfpgan && faceA?.id !== "gfpgan"
      ? describedByType.gfpgan
      : describedByType.restoreformer ?? describedByType.codeformer;
  const blend = describedByType.blend;
  if (!faceA || !faceB || !blend) return null;
  const nA = createDagNode(faceA, 60, 100);
  const nB = createDagNode(faceB, 60, 280);
  const nBlend = createDagNode(blend, 340, 190);
  nBlend.params = { alpha: 0.5, mode: "normal" };
  return {
    nodes: [nA, nB, nBlend],
    edges: [
      { id: "e0", from: nA.id, to: nBlend.id, toInput: "image" },
      { id: "e1", from: nB.id, to: nBlend.id, toInput: "image_b" },
    ],
  };
}
