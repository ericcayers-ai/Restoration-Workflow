import { describe, expect, it } from "vitest";
import { dagToPipeline, pipelineToDag } from "./pipelineDag";
import { pipelineToStages, stagesToPipeline, type Stage } from "./pipelineStages";
import type { DescribedNode, PipelineJson } from "./types";

function described(id: string, display = id): DescribedNode {
  return {
    id,
    display_name: display,
    description: "",
    category: "regression",
    vram_tier: "low",
    uses_gpu: false,
    supports_tiling: false,
    license: {
      spdx_id: "MIT",
      kind: "permissive",
      source_url: "https://example.invalid",
      requires_acknowledgement: false,
    },
    param_schema: { type: "object", properties: {} },
    weight_manifest: [],
    weights: {
      node_id: id,
      installed: true,
      acknowledged: true,
      requires_acknowledgement: false,
      total_size_bytes: 0,
      missing_size_bytes: 0,
      files: [],
    },
    availability: { state: "available", reason: null, badge: null },
  };
}

function stage(partial: Partial<Stage> & Pick<Stage, "id" | "nodeType">): Stage {
  return {
    displayName: partial.nodeType,
    category: "regression",
    params: {},
    pinned: false,
    ...partial,
  };
}

describe("list/graph round-trip", () => {
  it("stages ↔ pipeline preserves order and params", () => {
    const stages = [
      stage({ id: "a", nodeType: "scunet", params: { variant: "gan" }, displayName: "SCUNet" }),
      stage({ id: "b", nodeType: "realesrgan", params: { scale: 2 }, displayName: "RealESRGAN" }),
    ];
    const { pipeline, error } = stagesToPipeline(stages);
    expect(error).toBeNull();
    expect(pipeline.nodes.map((n) => n.type)).toEqual(["scunet", "realesrgan"]);
    expect(pipeline.edges).toEqual([{ from: "a", to: "b", to_input: "image" }]);

    const byType = { scunet: described("scunet", "SCUNet"), realesrgan: described("realesrgan") };
    const back = pipelineToStages(pipeline, byType);
    expect(back.map((s) => s.nodeType)).toEqual(["scunet", "realesrgan"]);
    expect(back[0]!.params).toEqual({ variant: "gan" });
  });

  it("list → DAG → list keeps identity", () => {
    const stages = [
      stage({ id: "n1", nodeType: "fbcnn" }),
      stage({ id: "n2", nodeType: "realesrgan", params: { scale: 4 } }),
    ];
    const { pipeline } = stagesToPipeline(stages);
    const byType = { fbcnn: described("fbcnn"), realesrgan: described("realesrgan") };
    const dag = pipelineToDag(pipeline, byType);
    const { pipeline: again, error } = dagToPipeline(dag.nodes, dag.edges);
    expect(error).toBeNull();
    expect(again.nodes).toEqual(pipeline.nodes);
    expect(again.edges).toEqual(pipeline.edges);
    expect(pipelineToStages(again, byType).map((s) => s.id)).toEqual(["n1", "n2"]);
  });

  it("mask side-channel survives list round-trip", () => {
    const stages = [
      stage({ id: "m", nodeType: "mask_from_image", category: "masking" }),
      stage({ id: "l", nodeType: "lama", category: "generative" }),
    ];
    const { pipeline, error } = stagesToPipeline(stages);
    expect(error).toBeNull();
    expect(pipeline.edges).toContainEqual({ from: "m", to: "l", to_input: "mask" });
  });

  it("load_mask wires to inpaint consumers", () => {
    const stages = [
      stage({ id: "m", nodeType: "load_mask", category: "masking" }),
      stage({ id: "l", nodeType: "powerpaint", category: "masking" }),
    ];
    const { pipeline, error } = stagesToPipeline(stages);
    expect(error).toBeNull();
    expect(pipeline.edges).toContainEqual({ from: "m", to: "l", to_input: "mask" });
  });

  it("rejects blend in linear list builder", () => {
    const { error } = stagesToPipeline([stage({ id: "b", nodeType: "blend", displayName: "Blend" })]);
    expect(error).toMatch(/merges two branches/i);
  });

  it("empty pipeline is empty", () => {
    const empty: PipelineJson = { version: 1, nodes: [], edges: [] };
    expect(pipelineToStages(empty, {})).toEqual([]);
    expect(stagesToPipeline([]).pipeline).toEqual(empty);
  });
});
