/*

 * REST client. Every call is a relative `/api/...` path — in dev the Vite

 * proxy forwards it to `restore serve`; in production the same build is

 * served *by* that backend, same origin (ARCHITECTURE.md section 1) — this

 * file never hardcodes a host, so it needs no change between the two.

 */



import type {

  AutoPipeline,

  DescribedNode,

  Download,

  HardwareInfo,

  Job,

  PipelineJson,

  Preset,

  WeightsOverview,

  WeightsStatus,

} from "./types";



export class ApiError extends Error {

  readonly status: number;

  readonly kind: string | null;

  readonly fallback: string | null;



  constructor(status: number, detail: string, kind: string | null, fallback: string | null) {

    super(detail);

    this.name = "ApiError";

    this.status = status;

    this.kind = kind;

    this.fallback = fallback;

  }

}



async function unwrap<T>(response: Response): Promise<T> {

  if (response.ok) {

    // 204/202-with-no-body endpoints don't exist here, but guard anyway.

    const text = await response.text();

    return text ? (JSON.parse(text) as T) : (undefined as T);

  }



  let detail = response.statusText || `HTTP ${response.status}`;

  let kind: string | null = null;

  let fallback: string | null = null;

  try {

    const body = await response.json();

    // The engine's error handler shape: {error, detail, fallback}. Plain

    // FastAPI HTTPException shape: {detail}. Both are handled.

    detail = body.detail ?? detail;

    kind = body.error ?? null;

    fallback = body.fallback ?? null;

  } catch {

    // Non-JSON error body — keep the status-text fallback above.

  }

  throw new ApiError(response.status, detail, kind, fallback);

}



async function getJson<T>(path: string): Promise<T> {

  return unwrap<T>(await fetch(path));

}



async function deleteJson<T>(path: string): Promise<T> {

  return unwrap<T>(await fetch(path, { method: "DELETE" }));

}



async function putJson<T>(path: string, body: unknown): Promise<T> {

  return unwrap<T>(

    await fetch(path, {

      method: "PUT",

      headers: { "Content-Type": "application/json" },

      body: JSON.stringify(body),

    }),

  );

}



async function postJson<T>(path: string, body?: unknown): Promise<T> {

  return unwrap<T>(

    await fetch(path, {

      method: "POST",

      headers: body ? { "Content-Type": "application/json" } : undefined,

      body: body ? JSON.stringify(body) : undefined,

    }),

  );

}



async function postForm<T>(path: string, form: FormData): Promise<T> {

  return unwrap<T>(await fetch(path, { method: "POST", body: form }));

}



// -- meta --------------------------------------------------------------------



export function getHardware(): Promise<HardwareInfo> {

  return getJson("/api/hardware");

}



// -- nodes ---------------------------------------------------------------------



export function listNodes(): Promise<DescribedNode[]> {

  return getJson("/api/nodes");

}



export function getNode(nodeId: string): Promise<DescribedNode> {

  return getJson(`/api/nodes/${encodeURIComponent(nodeId)}`);

}



// -- analysis / jobs -----------------------------------------------------------



export function analyzeImage(
  file: File | Blob,
  qualityTier: "draft" | "balanced" | "high" = "balanced",
): Promise<AutoPipeline> {
  const form = new FormData();
  form.append("image", file);
  form.append("quality_tier", qualityTier);
  return postForm("/api/analyze", form);
}

// -- masks (Mask Editor) -------------------------------------------------------

export function uploadMask(mask: Blob): Promise<{ id: string; url: string }> {
  const form = new FormData();
  form.append("mask", mask, "mask.png");
  return postForm("/api/masks", form);
}

export function maskUrl(maskId: string): string {
  return `/api/masks/${encodeURIComponent(maskId)}`;
}

export async function detectScratchMask(image: File | Blob): Promise<Blob> {
  const form = new FormData();
  form.append("image", image);
  const response = await fetch("/api/masks/scratch", { method: "POST", body: form });
  if (!response.ok) {
    await unwrap(response);
  }
  return response.blob();
}

export function segmentMask(image: File | Blob): Promise<{ id: string; url: string }> {
  const form = new FormData();
  form.append("image", image);
  return postForm("/api/masks/segment", form);
}

export async function inpaintWithMask(
  image: File | Blob,
  mask: Blob,
  engine: "lama" | "powerpaint" | "flux_fill" = "lama",
  prompt = "clean photograph",
): Promise<Blob> {
  const form = new FormData();
  form.append("image", image);
  form.append("mask", mask, "mask.png");
  form.append("engine", engine);
  form.append("prompt", prompt);
  const response = await fetch("/api/masks/inpaint", { method: "POST", body: form });
  if (!response.ok) {
    await unwrap(response);
  }
  return response.blob();
}

export interface SubmitJobOptions {

  pipeline?: object;

  preset?: string;

}



export function submitJob(file: File | Blob, options: SubmitJobOptions = {}): Promise<Job> {

  const form = new FormData();

  form.append("image", file);

  if (options.pipeline) form.append("pipeline", JSON.stringify(options.pipeline));

  if (options.preset) form.append("preset", options.preset);

  return postForm("/api/jobs", form);

}



export function getJob(jobId: string): Promise<Job> {

  return getJson(`/api/jobs/${encodeURIComponent(jobId)}`);

}



export function listJobs(): Promise<Job[]> {

  return getJson("/api/jobs");

}



export function cancelJob(jobId: string): Promise<{ cancelled: boolean; state: string }> {

  return postJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`);

}



export function deleteJob(jobId: string): Promise<{ deleted: boolean }> {

  return deleteJson(`/api/jobs/${encodeURIComponent(jobId)}`);

}



export function cleanupJobs(): Promise<{ purged: number; remaining: number }> {

  return postJson("/api/jobs/cleanup");

}



export function jobResultUrl(jobId: string): string {

  return `/api/jobs/${encodeURIComponent(jobId)}/result`;

}



export function jobEventsUrl(jobId: string): string {

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";

  return `${protocol}//${window.location.host}/api/jobs/${encodeURIComponent(jobId)}/events`;

}



// -- weights -------------------------------------------------------------------



export function listWeights(): Promise<WeightsOverview> {

  return getJson("/api/weights");

}



export function acknowledgeLicense(nodeId: string): Promise<WeightsStatus> {

  return postJson(`/api/weights/${encodeURIComponent(nodeId)}/acknowledge`, { accepted: true });

}



export interface StartDownloadOptions {

  params?: Record<string, unknown>;

  all_variants?: boolean;

  filenames?: string[];

}



export function startDownload(

  nodeId: string,

  options: StartDownloadOptions = {},

): Promise<Download> {

  const body =

    options.params || options.all_variants || options.filenames

      ? {

          params: options.params ?? {},

          all_variants: options.all_variants ?? false,

          filenames: options.filenames,

        }

      : undefined;

  return postJson(`/api/weights/${encodeURIComponent(nodeId)}/download`, body);

}



export function getDownload(downloadId: string): Promise<Download> {

  return getJson(`/api/weights/downloads/${encodeURIComponent(downloadId)}`);

}



export function listDownloads(): Promise<Download[]> {

  return getJson("/api/weights/downloads");

}



export function cancelDownload(

  downloadId: string,

): Promise<{ cancelled: boolean; state: string; cancel_requested: boolean }> {

  return postJson(`/api/weights/downloads/${encodeURIComponent(downloadId)}/cancel`);

}



export function removeWeights(nodeId: string): Promise<{ removed: boolean }> {

  return deleteJson(`/api/weights/${encodeURIComponent(nodeId)}`);

}



export interface InstructirPromptPreset {

  id: string;

  title: string;

  instruction: string;

  ensemble_hint?: string;

  pairs_with_workflow?: string[];

}



export function listInstructirPrompts(): Promise<{

  version: number;

  count: number;

  presets: InstructirPromptPreset[];

}> {

  return getJson("/api/instructir/prompts");

}



export interface EnsemblePlan {

  chain: string[];

  params: Record<string, Record<string, unknown>>;

  append_instructir: boolean;

  instruction: string;

  prompt_preset_id: string | null;

  reasons: { node: string; reason: string }[];

  pipeline: PipelineJson;

}



export function buildGuidedEnsemble(body: {

  prompt_preset_id?: string | null;

  instruction?: string | null;

  mode?: string;

  profile?: Record<string, unknown> | null;

  image?: File | Blob | null;

}): Promise<EnsemblePlan> {

  if (body.image) {

    const form = new FormData();

    form.append("image", body.image);

    if (body.prompt_preset_id) form.append("prompt_preset_id", body.prompt_preset_id);

    if (body.instruction) form.append("instruction", body.instruction);

    if (body.mode) form.append("mode", body.mode);

    return postForm("/api/pipelines/ensemble", form);

  }

  return postJson("/api/pipelines/ensemble", {

    prompt_preset_id: body.prompt_preset_id ?? null,

    instruction: body.instruction ?? null,

    mode: body.mode ?? "guide_and_finish",

    profile: body.profile ?? null,

  });

}



// -- presets --------------------------------------------------------------------



export function listPresets(options: { includeGated?: boolean } = {}): Promise<Preset[]> {

  const includeGated = options.includeGated ?? true;

  const qs = includeGated ? "" : "?include_gated=false";

  return getJson(`/api/presets${qs}`);

}



export function getPreset(name: string): Promise<Preset> {

  return getJson(`/api/presets/${encodeURIComponent(name)}`);

}



export function savePreset(

  name: string,

  pipeline: object,

  description = "",

): Promise<Preset> {

  return putJson(`/api/presets/${encodeURIComponent(name)}`, { pipeline, description });

}



export function deletePreset(name: string): Promise<{ deleted: boolean }> {

  return deleteJson(`/api/presets/${encodeURIComponent(name)}`);

}



// -- pipeline building: auto-order + .txt workflows -----------------------------



export function autoOrderPipeline(

  nodeTypes: string[],

  params: Record<string, Record<string, unknown>> = {},

): Promise<PipelineJson> {

  return postJson("/api/pipelines/auto-order", { node_types: nodeTypes, params });

}



export function exportWorkflowText(

  pipeline: PipelineJson,

  name = "",

  description = "",

): Promise<{ text: string }> {

  return postJson("/api/workflows/export", { pipeline, name, description });

}



export function importWorkflowText(text: string): Promise<PipelineJson> {

  return postJson("/api/workflows/import", { text });

}


