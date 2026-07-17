/*
 * The Advanced pipeline builder is a straightforward ordered list of stages,
 * not a node graph — the list's top-to-bottom order *is* the execution order.
 * This module is the only place that turns that list into the backend's
 * PipelineJson (a DAG: nodes + edges) and back, mirroring the same one
 * documented exception the backend's own auto_order_pipeline() has:
 * `lama` needs a `mask` input, which the box's `mask_from_image` node
 * supplies as a side-channel that feeds `lama` directly rather than the main
 * chain (core/ordering.py's auto_order_pipeline does the same wiring).
 *
 * `blend` merges two independent branches, which a single ordered list has no
 * way to represent — it is deliberately left unsupported here rather than
 * half-supported; a pipeline that genuinely needs two branches is built as a
 * .txt workflow (core/workflow_text.py) and imported.
 */

import type { DescribedNode, EdgeSpecJson, NodeCategory, NodeSpecJson, PipelineJson } from "./types";

export interface Stage extends Record<string, unknown> {
  id: string;
  nodeType: string;
  displayName: string;
  category: NodeCategory;
  params: Record<string, unknown>;
  pinned: boolean;
  // Populated live from the job WebSocket while a run is in progress.
  runStatus?: "queued" | "loading_weights" | "running" | "done" | "error";
  runProgress?: number;
  previewUrl?: string | null;
  cached?: boolean;
}

const MASK_CONSUMERS = new Set(["lama", "powerpaint", "flux_fill"]);
const MASK_PROVIDERS = new Set(["mask_from_image", "load_mask"]);
const MASK_INPUT = "mask";
const IMAGE_INPUT = "image";
const UNSUPPORTED_LINEAR = new Set(["blend"]);

let stageCounter = 0;

export function createStage(described: DescribedNode): Stage {
  stageCounter += 1;
  const defaults: Record<string, unknown> = {};
  for (const [key, spec] of Object.entries(described.param_schema.properties)) {
    if ("default" in spec) defaults[key] = spec.default;
  }
  return {
    id: `${described.id}_${stageCounter}_${Date.now().toString(36)}`,
    nodeType: described.id,
    displayName: described.display_name,
    category: described.category,
    params: defaults,
    pinned: false,
  };
}

/** Reorders `pipeline.nodes` into the order they actually execute in, reading
 *  top-to-bottom: follow "image" edges from the head, threading in any
 *  side-channel provider (e.g. a mask source) right before the stage that
 *  consumes it, the way it will appear once turned back into a list. */
export function pipelineToStages(
  pipeline: PipelineJson,
  describedByType: Record<string, DescribedNode>,
): Stage[] {
  const byId = new Map(pipeline.nodes.map((n) => [n.id, n]));
  const imageIncoming = new Map<string, string>();
  const sideProviders = new Map<string, string[]>();
  for (const e of pipeline.edges) {
    if (e.to_input === IMAGE_INPUT) imageIncoming.set(e.to, e.from);
    else sideProviders.set(e.to, [...(sideProviders.get(e.to) ?? []), e.from]);
  }
  const consumedAsSide = new Set(Array.from(sideProviders.values()).flat());

  const order: string[] = [];
  const visited = new Set<string>();
  let current = pipeline.nodes.find(
    (n) => !imageIncoming.has(n.id) && !consumedAsSide.has(n.id),
  )?.id;

  while (current && !visited.has(current)) {
    visited.add(current);
    for (const providerId of sideProviders.get(current) ?? []) {
      if (!visited.has(providerId)) {
        order.push(providerId);
        visited.add(providerId);
      }
    }
    order.push(current);
    current = pipeline.edges.find((e) => e.from === current && e.to_input === IMAGE_INPUT)?.to;
  }
  for (const n of pipeline.nodes) {
    if (!visited.has(n.id)) order.push(n.id); // orphaned/unreachable — surfaced, not dropped
  }

  return order.map((id) => {
    const n = byId.get(id)!;
    const described = describedByType[n.type];
    return {
      id: n.id,
      nodeType: n.type,
      displayName: described?.display_name ?? n.type,
      category: described?.category ?? "orchestration",
      params: n.params,
      pinned: n.pinned,
    };
  });
}

export function stagesToPipeline(stages: Stage[]): { pipeline: PipelineJson; error: string | null } {
  if (stages.length === 0) {
    return { pipeline: { version: 1, nodes: [], edges: [] }, error: null };
  }

  for (const s of stages) {
    if (UNSUPPORTED_LINEAR.has(s.nodeType)) {
      return {
        pipeline: { version: 1, nodes: [], edges: [] },
        error: `"${s.displayName}" merges two branches, which this builder can't represent as a single ordered list. Remove it, or hand-edit a saved .txt workflow.`,
      };
    }
  }

  const maskStage = stages.find((s) => MASK_PROVIDERS.has(s.nodeType));
  const hasMaskConsumer = stages.some((s) => MASK_CONSUMERS.has(s.nodeType));
  if (maskStage && !hasMaskConsumer) {
    return {
      pipeline: { version: 1, nodes: [], edges: [] },
      error: `"${maskStage.displayName}" produces a mask but nothing in the workflow uses it — add an inpaint node (LaMa / PowerPaint / FLUX Fill), or remove it.`,
    };
  }

  const nodes: NodeSpecJson[] = stages.map((s) => ({
    id: s.id,
    type: s.nodeType,
    params: s.params,
    pinned: s.pinned,
  }));
  const edges: EdgeSpecJson[] = [];
  let prev: Stage | null = null;
  let error: string | null = null;

  for (const s of stages) {
    if (MASK_CONSUMERS.has(s.nodeType)) {
      if (maskStage) edges.push({ from: maskStage.id, to: s.id, to_input: MASK_INPUT });
      else
        error ??= `"${s.displayName}" needs a mask stage (Load mask / Mask from image) somewhere in the workflow to fill from.`;
    }
    if (MASK_PROVIDERS.has(s.nodeType)) {
      // Feeds a consumer's named input, not the main chain — the node right
      // after it in the list still chains from whatever came before this one.
      continue;
    }
    if (prev) edges.push({ from: prev.id, to: s.id, to_input: IMAGE_INPUT });
    prev = s;
  }

  return { pipeline: { version: 1, nodes, edges }, error };
}
