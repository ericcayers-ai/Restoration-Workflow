/*
 * Maps the real, technical node chain onto the darkroom stage language
 * (UI_DESIGN.md section 7: "Developing → Fixing → Washing → Done... mapped
 * under the hood to whatever real node chain was selected — so the user
 * always has a legible mental model even with zero technical knowledge of
 * which models ran"). Deliberately positional, not tied to any node's
 * category: a two-node chain and a five-node chain both progress through
 * exactly three named stages, smoothly, from the same per-node progress
 * events the WebSocket already streams.
 */

import type { MessageKey } from "./i18n";
import type { NodeStatus, ProgressEvent } from "./types";

export type Stage = "developing" | "fixing" | "washing" | "done" | "error" | "cancelled";

const STAGE_MESSAGE_KEY: Record<Stage, MessageKey> = {
  developing: "simple.stage.developing",
  fixing: "simple.stage.fixing",
  washing: "simple.stage.washing",
  done: "simple.stage.done",
  error: "simple.stage.error",
  cancelled: "simple.stage.cancelled",
};

// Fixed weight for "weights are loading" so a slow first-time weight load
// still visibly moves the needle instead of sitting at 0% for a long pause.
const LOADING_WEIGHT_FRACTION = 0.15;

function nodeContribution(status: NodeStatus | undefined, progress: number): number {
  switch (status) {
    case "done":
      return 1;
    case "loading_weights":
      return LOADING_WEIGHT_FRACTION;
    case "running":
      return LOADING_WEIGHT_FRACTION + (1 - LOADING_WEIGHT_FRACTION) * clamp01(progress);
    case "error":
    case "queued":
    case undefined:
      return status === "error" ? clamp01(progress) : 0;
  }
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function overallFraction(
  nodeIds: string[],
  byNode: Record<string, ProgressEvent>,
): number {
  if (nodeIds.length === 0) return 0;
  const sum = nodeIds.reduce((acc, id) => {
    const event = byNode[id];
    return acc + nodeContribution(event?.status, event?.progress ?? 0);
  }, 0);
  return sum / nodeIds.length;
}

export function completedCount(nodeIds: string[], byNode: Record<string, ProgressEvent>): number {
  return nodeIds.filter((id) => byNode[id]?.status === "done").length;
}

export function stageFor(fraction: number): Stage {
  if (fraction < 0.34) return "developing";
  if (fraction < 0.72) return "fixing";
  return "washing";
}

export function stageMessageKey(stage: Stage): MessageKey {
  return STAGE_MESSAGE_KEY[stage];
}
