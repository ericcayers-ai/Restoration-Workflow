export type QualityTier = "draft" | "balanced" | "high";

/*

 * Mirrors backend/src/restoration/{core,api,presets.py} JSON shapes exactly.

 * Kept as one file, deliberately un-generated: the backend has no OpenAPI

 * schema export yet, so this is hand-synced against api/app.py, core/types.py

 * and presets.py. If the two drift, the failure mode is a TypeScript error at

 * a call site, not a silent runtime mismatch.

 */



export type NodeCategory =

  | "generative"

  | "face"

  | "regression"

  | "masking"

  | "orchestration"

  | "instruct";



export type VramTier = "low" | "mid" | "high" | "very_high";



export type LicenseKind = "permissive" | "non_commercial" | "unclear" | "custom";



export interface LicenseInfo {

  spdx_id: string;

  kind: LicenseKind;

  source_url: string;

  requires_acknowledgement: boolean;

}



export interface WeightFile {

  filename: string;

  size_bytes: number;

  sha256: string | null;

  url: string | null;

  hf_repo_id: string | null;

  hf_filename: string | null;

}



export type AvailabilityState =

  | "available"

  | "available_tiled"

  | "available_quantized"

  | "unavailable";



export interface Availability {

  state: AvailabilityState;

  reason: string | null;

  badge: string | null;

}



export interface WeightFileStatus {

  filename: string;

  installed: boolean;

  size_bytes: number;

  declared_size_bytes: number;

  sha256: string | null;

  /** True when this file is required for the node's default variant/params. */

  required_for_defaults?: boolean;

}



export interface WeightsStatus {

  node_id: string;

  installed: boolean;

  files: WeightFileStatus[];

  total_size_bytes: number;

  /** Bytes still needed for the default variant (prefer over total when missing). */

  missing_size_bytes?: number;

  acknowledged: boolean;

  requires_acknowledgement: boolean;

}



export interface DescribedNode {

  id: string;

  category: NodeCategory;

  display_name: string;

  description: string;

  license: LicenseInfo;

  vram_tier: VramTier;

  // JSON Schema `{type: "object", properties: {...}}` — see JsonSchema below.

  param_schema: JsonSchema;

  weight_manifest: WeightFile[];

  supports_tiling: boolean;

  uses_gpu: boolean;

  availability: Availability;

  weights: WeightsStatus;

}



/** The subset of JSON Schema the backend's param_schema authors actually use. */

export interface JsonSchemaProperty {

  type: "string" | "integer" | "number" | "boolean" | (string | null)[];

  title?: string;

  description?: string;

  default?: unknown;

  enum?: (string | number)[];

  minimum?: number;

  maximum?: number;

}



export interface JsonSchema {

  type: "object";

  properties: Record<string, JsonSchemaProperty>;

  additionalProperties?: boolean;

}



export interface GpuDevice {

  index: number;

  name: string;

  total_vram_mb: number;

}



export interface HardwareInfo {

  backend: "cuda" | "mps" | "cpu";

  devices: GpuDevice[];

  max_vram_mb: number;

  torch_available: boolean;

  torch_version: string | null;

}



export interface DegradationProfile {

  width: number;

  height: number;

  min_dimension: number;

  blur_score: number;

  noise_score: number;

  jpeg_blockiness: number;

  mean_luma: number;

  dark_fraction: number;

  bright_fraction: number;

  face_count: number | null;

  low_light: boolean;

  blown_highlights: boolean;

  defect_score?: number;

  blur_anisotropy?: number;

  under_exposure?: number;

  over_exposure?: number;

  clip_fraction?: number;

  mean_saturation?: number;

  is_grayscale?: boolean;

  chroma_blockiness?: number;

  confidence?: Record<string, number>;

}



export interface RoutingReason {

  node: string;

  reason: string;

}



export interface RoutingDecision {

  chain: string[];

  params: Record<string, Record<string, unknown>>;

  reasons: RoutingReason[];

}



export interface NodeSpecJson {

  id: string;

  type: string;

  params: Record<string, unknown>;

  pinned: boolean;

}



export interface EdgeSpecJson {

  from: string;

  to: string;

  to_input: string;

}



export interface PipelineJson {

  version: number;

  nodes: NodeSpecJson[];

  edges: EdgeSpecJson[];

}



export interface AutoPipeline {

  profile: DegradationProfile;

  routing: RoutingDecision;

  pipeline: PipelineJson;

  missing_weights: string[];

}



export type JobState = "queued" | "running" | "done" | "error" | "cancelled";



export interface Job {

  id: string;

  state: JobState;

  created_at: number;

  started_at: number | null;

  finished_at: number | null;

  error: string | null;

  fallback: string | null;

  analysis: AutoPipeline | null;

  pipeline: PipelineJson;

  result_url: string | null;

  /** True when the job's event ring was truncated under retention pressure. */

  events_truncated?: boolean;

}



export type NodeStatus = "queued" | "loading_weights" | "running" | "done" | "error";



export interface ProgressEvent {

  node_id: string;

  status: NodeStatus;

  progress: number;

  message: string | null;

  preview_url: string | null;

  cached: boolean;

}



export interface PresetLicence {

  ready: boolean;

  unacknowledged_node_ids: string[];

  missing_weights?: string[];

}



export interface Preset {

  version: number;

  name: string;

  description: string;

  pipeline: PipelineJson;

  licence?: PresetLicence;

}



export type DownloadState = "running" | "done" | "error" | "cancelled";



export interface Download {

  id: string;

  node_id: string;

  state: DownloadState;

  filename: string | null;

  bytes_done: number;

  bytes_total: number;

  progress: number;

  error: string | null;

  started_at: number;

  finished_at: number | null;

  params?: Record<string, unknown>;

  all_variants?: boolean;

}



export interface WeightsOverview {

  cache_dir: string;

  nodes: WeightsStatus[];

  installed: { node_id: string; size_bytes: number }[];

  totals?: {

    missing_node_ids: string[];

    permissive: { count: number; bytes: number };

    restricted: { count: number; bytes: number };

    grand: { count: number; bytes: number };

  };

}


