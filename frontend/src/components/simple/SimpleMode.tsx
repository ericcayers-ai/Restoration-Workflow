/*
 * Simple Mode (UI_DESIGN.md section 7, ROADMAP.md Phase 2) — "drop a photo,
 * get it fixed," zero configuration. Every choice the auto-analyzer made is
 * still inspectable (the reasons disclosure, "Open in Studio") but none of
 * it blocks the default path: a first-time user with no models installed yet
 * still reaches a restored photo without being asked a single question —
 * missing weights are fetched automatically, visibly, not silently.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  analyzeImage,
  autoOrderPipeline,
  cancelJob,
  getJob,
  jobResultUrl,
  listNodes,
  submitJob,
} from "../../lib/api";
import { useRegisterCommands } from "../../lib/commands";
import { useT } from "../../lib/i18n";
import {
  createStage,
  pipelineToStages,
  stagesToPipeline,
  type Stage,
} from "../../lib/pipelineStages";
import { completedCount, overallFraction, stageFor, stageMessageKey } from "../../lib/stages";
import type { AutoPipeline, DescribedNode, Job, PipelineJson } from "../../lib/types";
import { useJobEvents } from "../../lib/useJobEvents";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "../common/Button";
import { DownloadRow } from "../common/DownloadRow";
import { StatusLine } from "../common/StatusLine";
import { ModelStackRail } from "../studio/ModelStackRail";
import { StageList } from "../studio/StageList";
import { ActionBar } from "./ActionBar";
import { DropZone } from "./DropZone";
import { JobLogPanel } from "./JobLogPanel";
import { LightTable } from "./LightTable";
import styles from "./SimpleMode.module.css";

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
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [batchIndex, setBatchIndex] = useState(0);
  const [batchTotal, setBatchTotal] = useState(0);

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

  useEffect(() => {
    listNodes()
      .then(setDescribedNodes)
      .catch(() => setDescribedNodes([]));
  }, []);

  useEffect(() => {
    return () => {
      if (beforeUrl) URL.revokeObjectURL(beforeUrl);
    };
  }, [beforeUrl]);

  // The WebSocket's job-level terminal event carries no result_url or error
  // detail (ARCHITECTURE.md section 2's event shape is deliberately minimal) —
  // once it fires, re-fetch the job for the fields that only exist once it's
  // actually finished.
  useEffect(() => {
    if (!jobEvents.terminal || !job) return;
    let cancelled = false;
    getJob(job.id)
      .then((updated) => {
        if (cancelled) return;
        setJob(updated);
        if (updated.state === "done") {
          setStatus("done");
        } else {
          setStatus("error");
          setErrorMessage(updated.error);
          setFallback(updated.fallback);
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
    setReviewError(null);
    setViewMode("slider");
    downloads.reset();
    setStatus("analyzing");

    try {
      const result = await analyzeImage(selected);
      setAuto(result);
      setReviewStages(pipelineToStages(result.pipeline, describedByType));
      setStatus("review");
    } catch (err) {
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
        const ok = await downloads.downloadAll(missing);
        if (!ok) {
          setStatus("error");
          setErrorMessage(
            Object.values(downloads.tracker).find((d) => d.state === "error")?.error ??
              "One of the models this pipeline needs failed to download.",
          );
          return;
        }
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
    setReviewStages((prev) => [...prev, createStage(described)]);
    setReviewError(null);
  };

  const onRemoveReviewStage = (stageId: string) => {
    setReviewStages((prev) => prev.filter((s) => s.id !== stageId));
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
      const updated = await getJob(jobId);
      if (updated.state === "done" || updated.state === "error" || updated.state === "cancelled") {
        return updated;
      }
      await new Promise((r) => setTimeout(r, 300));
    }
  }

  async function handleBatch(files: File[]) {
    setBatchTotal(files.length);
    for (let i = 0; i < files.length; i++) {
      setBatchIndex(i + 1);
      const selected = files[i]!;
      setFile(selected);
      if (beforeUrl) URL.revokeObjectURL(beforeUrl);
      setBeforeUrl(URL.createObjectURL(selected));
      setJob(null);
      setErrorMessage(null);
      setStatus("analyzing");
      try {
        const result = await analyzeImage(selected);
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
        setStatus(finished.state === "done" ? "done" : "error");
        if (finished.state !== "done") break;
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
    setReviewError(null);
    setBatchTotal(0);
  }

  function download(filename: string) {
    if (!job) return;
    const a = document.createElement("a");
    a.href = jobResultUrl(job.id);
    a.download = filename;
    a.click();
  }

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
              run: () => cancelJob(job.id),
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

  if (status === "idle") {
    return (
      <div className={styles.screen}>
        <DropZone onFile={handleFile} onFiles={(files) => void handleBatch(files)} />
      </div>
    );
  }

  if (status === "review") {
    return (
      <div className={styles.reviewScreen}>
        <header className={styles.reviewHeader}>
          <h2>{t("simple.review.title")}</h2>
          <p>{t("simple.review.subtitle")}</p>
        </header>
        {auto && auto.routing.reasons.length > 0 && (
          <details className={styles.reasons}>
            <summary>{t("simple.reasonsTitle")}</summary>
            <ul className={styles.reasonList}>
              {auto.routing.reasons.map((r, i) => (
                <li key={i}>
                  <span className="mono">{r.node}</span>: {r.reason}
                </li>
              ))}
            </ul>
          </details>
        )}
        <div className={styles.reviewBody}>
          {beforeUrl && <img className={styles.reviewThumb} src={beforeUrl} alt="" />}
          <ModelStackRail nodes={addableNodes} onAddNode={onAddReviewStage} />
          <StageList
            stages={reviewStages}
            selectedId={null}
            onSelect={() => {}}
            onMove={onMoveReviewStage}
            onRemove={onRemoveReviewStage}
            onAutoOrder={onAutoOrderReview}
            error={reviewError}
          />
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
        {auto && auto.routing.reasons.length > 0 && (
          <details className={styles.reasons}>
            <summary>{t("simple.reasonsTitle")}</summary>
            <ul className={styles.reasonList}>
              {auto.routing.reasons.map((r, i) => (
                <li key={i}>
                  <span className="mono">{r.node}</span>: {r.reason}
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
          onExport={() => download(`${file?.name.replace(/\.[^.]+$/, "") ?? "photo"}-restored.png`)}
          onCompare={() => setViewMode((m) => (m === "side-by-side" ? "slider" : "side-by-side"))}
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
        {beforeUrl && <img className={styles.previewImg} src={beforeUrl} alt="" />}
        <div className={styles.errorBox}>
          <StatusLine message={t("simple.error.detail", { message: errorMessage ?? "" })} tone="error" />
          {fallback && <p className={styles.fallback}>{fallback}</p>}
          <Button variant="primary" onClick={reset}>
            {t("simple.error.retry")}
          </Button>
        </div>
      </div>
    );
  }

  // analyzing | downloading | submitting | processing
  return (
    <div className={styles.working}>
      {beforeUrl && <img className={styles.previewImg} src={beforeUrl} alt="" />}

      {status === "analyzing" && <StatusLine message={t("simple.analyzing")} tone="active" busy />}

      {status === "downloading" && auto && (
        <>
          <StatusLine
            message={t("simple.missingWeights", { nodes: auto.missing_weights.join(", ") })}
            tone="active"
            busy
          />
          <div className={styles.downloads}>
            {auto.missing_weights.map((nodeId) => (
              <DownloadRow key={nodeId} nodeId={nodeId} download={downloads.tracker[nodeId]} />
            ))}
          </div>
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
          <JobLogPanel events={jobEvents.byNode} open />
          {batchTotal > 0 && (
            <StatusLine
              message={t("simple.batch.progress", { current: batchIndex, total: batchTotal })}
              tone="active"
            />
          )}
          {job && (
            <Button variant="ghost" size="small" onClick={() => cancelJob(job.id)}>
              {t("common.cancel")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}
