/*
 * Simple Mode (UI_DESIGN.md section 7, ROADMAP.md Phase 2) — "drop a photo,
 * get it fixed," zero configuration. Every choice the auto-analyzer made is
 * still inspectable (the reasons disclosure, "Open in Studio") but none of
 * it blocks the default path: a first-time user with no models installed yet
 * still reaches a restored photo without being asked a single question —
 * missing weights are fetched automatically, visibly, not silently.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  acknowledgeLicense,
  analyzeImage,
  autoOrderPipeline,
  cancelJob,
  getJob,
  getPreset,
  jobResultUrl,
  listNodes,
  listPresets,
  submitJob,
} from "../../lib/api";
import { useRegisterCommands } from "../../lib/commands";
import { formatConfidence } from "../../lib/format";
import { useT } from "../../lib/i18n";
import {
  createStage,
  pipelineToStages,
  stagesToPipeline,
  type Stage,
} from "../../lib/pipelineStages";
import { completedCount, overallFraction, stageFor, stageMessageKey } from "../../lib/stages";
import type {
  AutoPipeline,
  DescribedNode,
  Job,
  PipelineJson,
  Preset,
  QualityTier,
} from "../../lib/types";
import { useJobEvents } from "../../lib/useJobEvents";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "../common/Button";
import { DownloadRow } from "../common/DownloadRow";
import { FlowSteps, type FlowStepId } from "../common/FlowSteps";
import { StatusLine } from "../common/StatusLine";
import { Inspector } from "../studio/Inspector";
import { ModelStackRail } from "../studio/ModelStackRail";
import { StageList } from "../studio/StageList";
import { ActionBar } from "./ActionBar";
import { DropZone } from "./DropZone";
import { JobLogPanel } from "./JobLogPanel";
import { LightTable } from "./LightTable";
import styles from "./SimpleMode.module.css";

const FLOW_STEPS: FlowStepId[] = ["drop", "review", "restore"];

type Status =
  | "idle"
  | "analyzing"
  | "review"
  | "downloading"
  | "submitting"
  | "processing"
  | "done"
  | "error";

function missingWeightsFor(
  pipeline: PipelineJson,
  describedByType: Record<string, DescribedNode>,
): string[] {
  const seen = new Set<string>();
  const missing: string[] = [];
  for (const n of pipeline.nodes) {
    if (seen.has(n.type)) continue;
    seen.add(n.type);
    const described = describedByType[n.type];
    if (described && !described.weights.installed) missing.push(n.type);
  }
  return missing;
}

type ViewMode = "slider" | "side-by-side" | "difference";

export function SimpleMode({
  onOpenInStudio,
}: {
  onOpenInStudio: (pipeline: PipelineJson, file: File) => void;
}) {
  const t = useT();
  const [status, setStatus] = useState<Status>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [beforeUrl, setBeforeUrl] = useState<string | null>(null);
  const [auto, setAuto] = useState<AutoPipeline | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fallback, setFallback] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("slider");
  const [describedNodes, setDescribedNodes] = useState<DescribedNode[]>([]);
  const [reviewStages, setReviewStages] = useState<Stage[]>([]);
  const [reviewSelectedId, setReviewSelectedId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [batchIndex, setBatchIndex] = useState(0);
  const [batchTotal, setBatchTotal] = useState(0);
  const batchCancelRef = useRef(false);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetChoice, setPresetChoice] = useState("");
  const [qualityTier, setQualityTier] = useState<QualityTier>("balanced");
  const [showGatedPresets, setShowGatedPresets] = useState(false);
  const [liveMessage, setLiveMessage] = useState("");

  const downloads = useWeightDownloads();
  const jobEvents = useJobEvents(job?.id ?? null);

  const describedByType = useMemo(
    () => Object.fromEntries(describedNodes.map((n) => [n.id, n])),
    [describedNodes],
  );
  // Simple Mode's default guarantee is that it never runs a non-permissive
  // model without the explicit license-acknowledgement UI Studio Mode has;
  // customizing the auto-picked chain here must not quietly break that, so
  // the add-a-model list only offers permissive nodes.
  const addableNodes = useMemo(
    () => describedNodes.filter((n) => !n.license.requires_acknowledgement),
    [describedNodes],
  );

  const visiblePresets = useMemo(() => {
    if (showGatedPresets) return presets;
    return presets.filter((p) => p.licence?.ready !== false);
  }, [presets, showGatedPresets]);

  useEffect(() => {
    listNodes()
      .then(setDescribedNodes)
      .catch(() => setDescribedNodes([]));
    listPresets({ includeGated: true })
      .then(setPresets)
      .catch(() => setPresets([]));
  }, []);

  useEffect(() => {
    return () => {
      if (beforeUrl) URL.revokeObjectURL(beforeUrl);
    };
  }, [beforeUrl]);

  useEffect(() => {
    if (jobEvents.connectionLost && status === "processing") {
      setStatus("error");
      setErrorMessage(t("simple.error.connectionLost"));
      setLiveMessage(t("simple.error.connectionLost"));
    }
  }, [jobEvents.connectionLost, status, t]);

  // The WebSocket's job-level terminal event carries no result_url or error
  // detail — once it fires, re-fetch the job for the fields that only exist
  // once it's actually finished.
  useEffect(() => {
    if (!jobEvents.terminal || !job) return;
    let cancelled = false;
    getJob(job.id)
      .then((updated) => {
        if (cancelled) return;
        setJob(updated);
        if (updated.state === "done") {
          setStatus("done");
          setLiveMessage(t("simple.stage.done"));
        } else if (updated.state === "cancelled") {
          setStatus("error");
          setErrorMessage(t("simple.stage.cancelled"));
          setLiveMessage(t("simple.stage.cancelled"));
        } else {
          setStatus("error");
          setErrorMessage(updated.error);
          setFallback(updated.fallback);
          setLiveMessage(updated.error ?? t("simple.stage.error"));
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(err instanceof ApiError ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobEvents.terminal]);

  async function submitPipeline(selected: File, pipeline: PipelineJson) {
    setStatus("submitting");
    try {
      const submitted = await submitJob(selected, { pipeline });
      setJob(submitted);
      setStatus("processing");
      setLiveMessage(t("simple.stage.developing"));
    } catch (err) {
      setStatus("error");
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
      setFallback(err instanceof ApiError ? err.fallback : null);
    }
  }

  async function handleFile(selected: File) {
    setFile(selected);
    setBeforeUrl(URL.createObjectURL(selected));
    setJob(null);
    setErrorMessage(null);
    setFallback(null);
    setAuto(null);
    setReviewStages([]);
    setReviewSelectedId(null);
    setReviewError(null);
    setViewMode("slider");
    downloads.reset();
    setStatus("analyzing");
    setLiveMessage(t("simple.analyzing"));

    try {
      if (presetChoice) {
        const preset = await getPreset(presetChoice);
        if (preset.licence && !preset.licence.ready) {
          setStatus("error");
          setErrorMessage(
            t("simple.error.licenceGate", {
              nodes: preset.licence.unacknowledged_node_ids.join(", "),
            }),
          );
          return;
        }
        const stages = pipelineToStages(preset.pipeline, describedByType);
        setAuto({
          profile: {
            width: 0,
            height: 0,
            min_dimension: 0,
            blur_score: 0,
            noise_score: 0,
            jpeg_blockiness: 0,
            mean_luma: 0.5,
            dark_fraction: 0,
            bright_fraction: 0,
            face_count: null,
            low_light: false,
            blown_highlights: false,
          },
          routing: {
            chain: stages.map((s) => s.nodeType),
            params: {},
            reasons: [
              {
                node: presetChoice,
                reason: `workflow preset "${presetChoice}" — ${preset.description || "user-selected"}`,
              },
            ],
          },
          pipeline: preset.pipeline,
          missing_weights: [] as string[],
        });
        setReviewStages(stages);
        setStatus("review");
      } else {
        const result = await analyzeImage(selected, qualityTier);
        setAuto(result);
        setReviewStages(pipelineToStages(result.pipeline, describedByType));
        setStatus("review");
      }
    } catch (err) {
      // Recoverable analyze errors keep the file so the user can retry.
      setStatus("error");
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function proceedFromReview() {
    if (!file) return;
    const { pipeline, error } = stagesToPipeline(reviewStages);
    if (error) {
      setReviewError(error);
      return;
    }
    if (pipeline.nodes.length === 0) {
      setReviewError(t("pipeline.stages.empty"));
      return;
    }
    setReviewError(null);
    try {
      const missing = missingWeightsFor(pipeline, describedByType);
      if (missing.length > 0) {
        setStatus("downloading");
        setLiveMessage(
          t("simple.missingWeights", {
            nodes: missing.map((id) => describedByType[id]?.display_name ?? id).join(", "),
          }),
        );
        const ok = await downloads.downloadAll(missing);
        if (!ok) {
          setStatus("error");
          setErrorMessage(
            Object.values(downloads.tracker).find((d) => d.state === "error")?.error ??
              t("simple.error.downloadFailed"),
          );
          return;
        }
        // Refresh install flags for subsequent runs.
        const refreshed = await listNodes();
        setDescribedNodes(refreshed);
      }
      await submitPipeline(file, pipeline);
    } catch (err) {
      setStatus("error");
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    }
  }

  const onAddReviewStage = (nodeTypeId: string) => {
    const described = describedByType[nodeTypeId];
    if (!described) return;
    const stage = createStage(described);
    setReviewStages((prev) => [...prev, stage]);
    setReviewSelectedId(stage.id);
    setReviewError(null);
  };

  const onRemoveReviewStage = (stageId: string) => {
    setReviewStages((prev) => prev.filter((s) => s.id !== stageId));
    if (reviewSelectedId === stageId) setReviewSelectedId(null);
  };

  const onMoveReviewStage = (stageId: string, direction: -1 | 1) => {
    setReviewStages((prev) => {
      const index = prev.findIndex((s) => s.id === stageId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target]!, next[index]!];
      return next;
    });
  };

  const onAutoOrderReview = () => {
    if (reviewStages.length < 2) return;
    const params: Record<string, Record<string, unknown>> = {};
    for (const s of reviewStages) params[s.nodeType] = s.params;
    autoOrderPipeline(
      reviewStages.map((s) => s.nodeType),
      params,
    )
      .then((pipeline) => {
        setReviewStages(pipelineToStages(pipeline, describedByType));
        setReviewError(null);
      })
      .catch((err) => setReviewError(err instanceof ApiError ? err.message : String(err)));
  };

  async function waitForJob(jobId: string): Promise<Job> {
    while (true) {
      if (batchCancelRef.current) {
        await cancelJob(jobId);
        const cancelled = await getJob(jobId);
        return cancelled;
      }
      const updated = await getJob(jobId);
      if (updated.state === "done" || updated.state === "error" || updated.state === "cancelled") {
        return updated;
      }
      await new Promise((r) => setTimeout(r, 300));
    }
  }

  async function handleBatch(files: File[]) {
    batchCancelRef.current = false;
    setBatchTotal(files.length);
    // Safe batch preflight: collect unique missing weights across first-pass
    // analyze of each file would be expensive — analyze the first, then download
    // those missing, and re-check per image as we go.
    try {
      const first = files[0]!;
      const probe = await analyzeImage(first, qualityTier);
      const probeMissing = missingWeightsFor(probe.pipeline, describedByType);
      if (probeMissing.length > 0) {
        setStatus("downloading");
        setLiveMessage(
          t("simple.error.batchPreflight", {
            count: probeMissing.length,
            nodes: probeMissing.map((id) => describedByType[id]?.display_name ?? id).join(", "),
          }),
        );
        const ok = await downloads.downloadAll(probeMissing);
        if (!ok) {
          setStatus("error");
          setErrorMessage(t("simple.error.downloadFailed"));
          setBatchTotal(0);
          return;
        }
        setDescribedNodes(await listNodes());
      }
    } catch (err) {
      setStatus("error");
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
      setBatchTotal(0);
      return;
    }

    for (let i = 0; i < files.length; i++) {
      if (batchCancelRef.current) break;
      setBatchIndex(i + 1);
      const selected = files[i]!;
      setFile(selected);
      if (beforeUrl) URL.revokeObjectURL(beforeUrl);
      setBeforeUrl(URL.createObjectURL(selected));
      setJob(null);
      setErrorMessage(null);
      setStatus("analyzing");
      try {
        const result = await analyzeImage(selected, qualityTier);
        setAuto(result);
        const stages = pipelineToStages(result.pipeline, describedByType);
        setReviewStages(stages);
        const { pipeline, error } = stagesToPipeline(stages);
        if (error) break;
        const missing = missingWeightsFor(pipeline, describedByType);
        if (missing.length > 0) {
          setStatus("downloading");
          const ok = await downloads.downloadAll(missing);
          if (!ok) break;
        }
        setStatus("submitting");
        const submitted = await submitJob(selected, { pipeline });
        setJob(submitted);
        setStatus("processing");
        const finished = await waitForJob(submitted.id);
        setJob(finished);
        if (finished.state === "cancelled" || batchCancelRef.current) {
          setStatus("error");
          setErrorMessage(t("simple.batch.cancelled"));
          break;
        }
        setStatus(finished.state === "done" ? "done" : "error");
        if (finished.state !== "done") {
          setErrorMessage(finished.error);
          break;
        }
      } catch (err) {
        setStatus("error");
        setErrorMessage(err instanceof ApiError ? err.message : String(err));
        break;
      }
    }
    setBatchTotal(0);
  }

  function tryAgain() {
    if (!file) return;
    setJob(null);
    setErrorMessage(null);
    setFallback(null);
    setStatus("review");
  }

  function reset() {
    setStatus("idle");
    setFile(null);
    setBeforeUrl(null);
    setAuto(null);
    setJob(null);
    setErrorMessage(null);
    setFallback(null);
    setReviewStages([]);
    setReviewSelectedId(null);
    setReviewError(null);
    setBatchTotal(0);
    batchCancelRef.current = false;
  }

  function download(filename: string) {
    if (!job) return;
    const a = document.createElement("a");
    a.href = jobResultUrl(job.id);
    a.download = filename;
    a.click();
  }

  const reviewSelected = useMemo(
    () => reviewStages.find((s) => s.id === reviewSelectedId) ?? null,
    [reviewStages, reviewSelectedId],
  );
  const reviewDescribed = reviewSelected ? (describedByType[reviewSelected.nodeType] ?? null) : null;

  const stageInfo = useMemo(() => {
    if (!job) return null;
    const ids = job.pipeline.nodes.map((n) => n.id);
    const fraction = overallFraction(ids, jobEvents.byNode);
    const stage = status === "error" ? "error" : stageFor(fraction);
    return {
      stage,
      message: t(stageMessageKey(stage)),
      step: Math.min(completedCount(ids, jobEvents.byNode) + 1, ids.length),
      total: ids.length,
    };
  }, [job, jobEvents.byNode, status, t]);

  const reasonLines = useMemo(() => {
    if (!auto) return [];
    return auto.routing.reasons.map((r) => {
      const display = describedByType[r.node]?.display_name ?? r.node;
      const confidence = auto.profile.confidence?.[r.node];
      const confLabel = formatConfidence(confidence);
      return {
        node: display,
        reason: r.reason,
        confidence: confLabel,
      };
    });
  }, [auto, describedByType]);

  const flowLabels = useMemo(
    () => ({
      drop: t("simple.flow.drop"),
      review: t("simple.flow.review"),
      restore: t("simple.flow.restore"),
    }),
    [t],
  );

  const flowCurrent: FlowStepId =
    status === "idle"
      ? "drop"
      : status === "review"
        ? "review"
        : "restore";

  const commands = useMemo(
    () => [
      ...(status === "done" || status === "error"
        ? [
            {
              id: "simple.reset",
              label: t("simple.action.reset"),
              category: "Simple Mode",
              icon: "upload" as const,
              run: reset,
            },
          ]
        : []),
      ...(status === "done" && job && file
        ? [
            {
              id: "simple.open-in-studio",
              label: t("simple.action.openInStudio"),
              category: "Simple Mode",
              icon: "flow" as const,
              run: () => onOpenInStudio(job.pipeline, file),
            },
          ]
        : []),
      ...(status === "processing" && job
        ? [
            {
              id: "simple.cancel",
              label: t("common.cancel"),
              category: "Simple Mode",
              icon: "close" as const,
              run: () => {
                batchCancelRef.current = true;
                void cancelJob(job.id);
              },
            },
          ]
        : []),
      ...(status === "review"
        ? [
            {
              id: "simple.review.run",
              label: t("simple.review.run"),
              category: "Simple Mode",
              icon: "play" as const,
              run: (): void => {
                void proceedFromReview();
              },
            },
            {
              id: "simple.review.auto-order",
              label: t("pipeline.stages.autoOrder"),
              category: "Simple Mode",
              icon: "sort" as const,
              run: onAutoOrderReview,
            },
          ]
        : []),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [status, job, file, reviewStages],
  );
  useRegisterCommands("simple-mode", commands);

  const liveRegion = (
    <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
      {liveMessage}
    </div>
  );

  if (status === "idle") {
    return (
      <div className={styles.screen}>
        {liveRegion}
        <FlowSteps steps={FLOW_STEPS} current={flowCurrent} labels={flowLabels} ariaLabel={t("simple.flow.progress")} />
        <DropZone onFile={handleFile} onFiles={(files) => void handleBatch(files)} />
        <div className={styles.optionsBar}>
          <div className={styles.qualityField}>
            <span id="simple-quality-label">{t("simple.quality.label")}</span>
            <div
              className={styles.qualitySegmented}
              role="radiogroup"
              aria-labelledby="simple-quality-label"
              title={t("simple.quality.hint")}
            >
              {(["draft", "balanced", "high"] as QualityTier[]).map((tier) => (
                <button
                  key={tier}
                  type="button"
                  role="radio"
                  aria-checked={qualityTier === tier}
                  className={qualityTier === tier ? styles.qualityActive : styles.qualityTab}
                  onClick={() => setQualityTier(tier)}
                >
                  {t(`simple.quality.${tier}`)}
                </button>
              ))}
            </div>
          </div>
          {presets.length > 0 && (
            <details className={styles.presetDetails}>
              <summary>{t("simple.presets.title")}</summary>
              <label className={styles.presetField}>
                <span className="visually-hidden">{t("simple.presets.load")}</span>
                <select
                  value={presetChoice}
                  onChange={(e) => setPresetChoice(e.target.value)}
                  aria-label={t("simple.presets.load")}
                >
                  <option value="">{t("simple.presets.none")}</option>
                  {visiblePresets.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.licence && !p.licence.ready
                        ? t("simple.presets.gated", { name: p.name })
                        : p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.gatedToggle}>
                <input
                  type="checkbox"
                  checked={showGatedPresets}
                  onChange={(e) => setShowGatedPresets(e.target.checked)}
                />
                <span>{t("simple.presets.showGated")}</span>
              </label>
            </details>
          )}
        </div>
      </div>
    );
  }

  if (status === "review") {
    return (
      <div className={styles.reviewScreen}>
        {liveRegion}
        <FlowSteps steps={FLOW_STEPS} current={flowCurrent} labels={flowLabels} ariaLabel={t("simple.flow.progress")} />
        <header className={styles.reviewHeader}>
          <h2>{t("simple.review.title")}</h2>
          <p>{t("simple.review.subtitle")}</p>
        </header>
        {reasonLines.length > 0 && (
          <details className={styles.reasons}>
            <summary>{t("simple.reasonsTitle")}</summary>
            <ul className={styles.reasonList}>
              {reasonLines.map((r, i) => (
                <li key={i}>
                  <span className="mono">{r.node}</span>: {r.reason}
                  {r.confidence
                    ? ` (${t("simple.reasons.confidence", { value: r.confidence })})`
                    : ""}
                </li>
              ))}
            </ul>
          </details>
        )}
        <div className={styles.reviewBody}>
          {beforeUrl && (
            <img
              className={styles.reviewThumb}
              src={beforeUrl}
              alt=""
            />
          )}
          <ModelStackRail nodes={addableNodes} onAddNode={onAddReviewStage} />
          <StageList
            stages={reviewStages}
            selectedId={reviewSelectedId}
            onSelect={setReviewSelectedId}
            onMove={onMoveReviewStage}
            onRemove={onRemoveReviewStage}
            onAutoOrder={onAutoOrderReview}
            error={reviewError}
          />
          <div className={styles.reviewInspector}>
            <Inspector
              selectedStage={reviewSelected}
              described={reviewDescribed}
              onParamsChange={(stageId, params) => {
                setReviewStages((prev) =>
                  prev.map((s) => (s.id === stageId ? { ...s, params } : s)),
                );
              }}
              onPinnedChange={(stageId, pinned) => {
                setReviewStages((prev) =>
                  prev.map((s) => (s.id === stageId ? { ...s, pinned } : s)),
                );
              }}
              downloads={downloads}
              onAcknowledge={(nodeId) => {
                void acknowledgeLicense(nodeId).then((status) => {
                  setDescribedNodes((list) =>
                    list.map((n) => (n.id === nodeId ? { ...n, weights: status } : n)),
                  );
                });
              }}
              onWeightsChanged={() => {
                void listNodes().then(setDescribedNodes);
              }}
            />
          </div>
        </div>
        <div className={styles.reviewActions}>
          <Button variant="ghost" onClick={reset}>
            {t("simple.review.back")}
          </Button>
          <Button
            variant="primary"
            icon="play"
            onClick={() => void proceedFromReview()}
            disabled={reviewStages.length === 0}
          >
            {t("simple.review.run")}
          </Button>
        </div>
      </div>
    );
  }

  if (status === "done" && job && beforeUrl) {
    return (
      <div className={styles.resultScreen}>
        {liveRegion}
        <FlowSteps steps={FLOW_STEPS} current="restore" labels={flowLabels} complete ariaLabel={t("simple.flow.progress")} />
        {reasonLines.length > 0 && (
          <details className={styles.reasons}>
            <summary>{t("simple.reasonsTitle")}</summary>
            <ul className={styles.reasonList}>
              {reasonLines.map((r, i) => (
                <li key={i}>
                  <span className="mono">{r.node}</span>: {r.reason}
                  {r.confidence
                    ? ` (${t("simple.reasons.confidence", { value: r.confidence })})`
                    : ""}
                </li>
              ))}
            </ul>
          </details>
        )}
        <LightTable
          beforeUrl={beforeUrl}
          afterUrl={jobResultUrl(job.id)}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          reveal
        />
        <ActionBar
          onSave={() => download("restored.png")}
          onExport={() =>
            download(`${file?.name.replace(/\.[^.]+$/, "") ?? "photo"}-restored.png`)
          }
          onOpenInStudio={() => file && onOpenInStudio(job.pipeline, file)}
          onReset={reset}
          onTryAgain={tryAgain}
        />
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className={styles.working}>
        {liveRegion}
        <FlowSteps steps={FLOW_STEPS} current={flowCurrent} labels={flowLabels} ariaLabel={t("simple.flow.progress")} />
        {beforeUrl && (
          <img className={styles.previewImg} src={beforeUrl} alt="" />
        )}
        <div className={styles.errorBox}>
          <StatusLine
            message={t("simple.error.detail", { message: errorMessage ?? "" })}
            tone="error"
          />
          {fallback && <p className={styles.fallback}>{fallback}</p>}
          {reviewStages.length > 0 && (
            <Button variant="primary" onClick={tryAgain}>
              {t("simple.error.backToReview")}
            </Button>
          )}
          <Button variant="ghost" onClick={reset}>
            {t("simple.error.retry")}
          </Button>
        </div>
      </div>
    );
  }

  // analyzing | downloading | submitting | processing
  const downloadingIds =
    Object.keys(downloads.tracker).length > 0
      ? Object.keys(downloads.tracker)
      : (auto?.missing_weights ?? []);

  return (
    <div className={styles.working}>
      {liveRegion}
      <FlowSteps steps={FLOW_STEPS} current={flowCurrent} labels={flowLabels} ariaLabel={t("simple.flow.progress")} />
      {beforeUrl && (
        <img className={styles.previewImg} src={beforeUrl} alt="" />
      )}

      <div className={styles.progressMeta}>
        {status === "analyzing" && <StatusLine message={t("simple.analyzing")} tone="active" busy />}

        {status === "downloading" && (
          <>
            <StatusLine
              message={t("simple.missingWeights", {
                nodes: downloadingIds
                  .map((id) => describedByType[id]?.display_name ?? id)
                  .join(", "),
              })}
              tone="active"
              busy
            />
            <div className={styles.downloads}>
              {downloadingIds.map((nodeId) => (
                <DownloadRow
                  key={nodeId}
                  nodeId={nodeId}
                  displayName={describedByType[nodeId]?.display_name}
                  download={downloads.tracker[nodeId]}
                  onCancel={() => void downloads.cancel(nodeId)}
                />
              ))}
            </div>
            <Button variant="ghost" size="small" onClick={() => void downloads.cancel()}>
              {t("settings.downloads.cancelAll")}
            </Button>
          </>
        )}

        {status === "submitting" && <StatusLine message={t("common.loading")} tone="active" busy />}

        {status === "processing" && stageInfo && (
          <>
            <StatusLine
              message={`${stageInfo.message} — ${stageInfo.step}/${stageInfo.total}`}
              tone="active"
              busy
            />
            {job?.events_truncated && (
              <StatusLine message={t("studio.eventsTruncated")} />
            )}
            <JobLogPanel events={jobEvents.byNode} open />
            {batchTotal > 0 && (
              <StatusLine
                message={t("simple.batch.progress", { current: batchIndex, total: batchTotal })}
                tone="active"
              />
            )}
            {job && (
              <Button
                variant="ghost"
                size="small"
                onClick={() => {
                  batchCancelRef.current = true;
                  void cancelJob(job.id);
                }}
              >
                {t("common.cancel")}
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

