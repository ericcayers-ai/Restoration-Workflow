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
  cancelJob,
  getJob,
  jobResultUrl,
  submitJob,
} from "../../lib/api";
import { useRegisterCommands } from "../../lib/commands";
import { useT } from "../../lib/i18n";
import { completedCount, overallFraction, stageFor, stageMessageKey } from "../../lib/stages";
import type { AutoPipeline, Job, PipelineJson } from "../../lib/types";
import { useJobEvents } from "../../lib/useJobEvents";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "../common/Button";
import { DownloadRow } from "../common/DownloadRow";
import { StatusLine } from "../common/StatusLine";
import { ActionBar } from "./ActionBar";
import { DropZone } from "./DropZone";
import { LightTable } from "./LightTable";
import styles from "./SimpleMode.module.css";

type Status =
  | "idle"
  | "analyzing"
  | "downloading"
  | "submitting"
  | "processing"
  | "done"
  | "error";

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

  const downloads = useWeightDownloads();
  const jobEvents = useJobEvents(job?.id ?? null);

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

  async function submitPipeline(selected: File, autoResult: AutoPipeline) {
    setStatus("submitting");
    try {
      const submitted = await submitJob(selected, { pipeline: autoResult.pipeline });
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
    setViewMode("slider");
    downloads.reset();
    setStatus("analyzing");

    try {
      const result = await analyzeImage(selected);
      setAuto(result);
      if (result.missing_weights.length > 0) {
        setStatus("downloading");
        const ok = await downloads.downloadAll(result.missing_weights);
        if (!ok) {
          setStatus("error");
          setErrorMessage(
            Object.values(downloads.tracker).find((d) => d.state === "error")?.error ??
              "One of the models this pipeline needs failed to download.",
          );
          return;
        }
      }
      await submitPipeline(selected, result);
    } catch (err) {
      setStatus("error");
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    }
  }

  function reset() {
    setStatus("idle");
    setFile(null);
    setBeforeUrl(null);
    setAuto(null);
    setJob(null);
    setErrorMessage(null);
    setFallback(null);
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
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [status, job, file],
  );
  useRegisterCommands("simple-mode", commands);

  if (status === "idle") {
    return (
      <div className={styles.screen}>
        <DropZone onFile={handleFile} />
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
        />
        <ActionBar
          onSave={() => download("restored.png")}
          onExport={() => download(`${file?.name.replace(/\.[^.]+$/, "") ?? "photo"}-restored.png`)}
          onCompare={() => setViewMode((m) => (m === "side-by-side" ? "slider" : "side-by-side"))}
          onOpenInStudio={() => file && onOpenInStudio(job.pipeline, file)}
          onReset={reset}
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
