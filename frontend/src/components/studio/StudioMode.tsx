/*
 * Studio Mode (UI_DESIGN.md section 8, ROADMAP.md Phase 3) — every choice
 * Simple Mode made, made visible and editable, plus the power to build any
 * pipeline the full model stack supports. List and graph editors share one
 * canonical PipelineJson so parameter edits and topology survive mode switches.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  acknowledgeLicense,
  autoOrderPipeline,
  autoSuggest,
  buildGuidedEnsemble,
  cancelJob,
  exportWorkflowText,
  getJob,
  getNode,
  getPreset,
  importWorkflowText,
  jobResultUrl,
  listInstructirPrompts,
  listNodes,
  savePreset,
  submitJob,
} from "../../lib/api";
import { waitForJobDone } from "../../lib/batchJobs";
import { useRegisterCommands } from "../../lib/commands";
import { useT } from "../../lib/i18n";
import {
  createDagNode,
  dagToPipeline,
  dualFaceBlendTemplate,
  pipelineToDag,
  type DagEdge,
  type DagNode,
} from "../../lib/pipelineDag";
import {
  createStage,
  pipelineToStages,
  stagesToPipeline,
  type Stage,
} from "../../lib/pipelineStages";
import type { DescribedNode, Job, PipelineJson, SuggestedPreset } from "../../lib/types";
import { useJobEvents } from "../../lib/useJobEvents";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "../common/Button";
import { StatusLine } from "../common/StatusLine";
import { ActionBar } from "../simple/ActionBar";
import { LightTable } from "../simple/LightTable";
import { ContactSheet, type RunRecord } from "./ContactSheet";
import { Inspector } from "./Inspector";
import { ModelStackRail } from "./ModelStackRail";
import { PipelineCanvas } from "./PipelineCanvas";
import { PresetBar } from "./PresetBar";
import { StageList } from "./StageList";
import styles from "./StudioMode.module.css";

export interface StudioHandoff {
  pipeline: PipelineJson;
  file: File;
  token: number;
}

type Easel = "rail" | "workflow" | "inspector";

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

export function StudioMode({ handoff }: { handoff: StudioHandoff | null }) {
  const t = useT();
  const [describedNodes, setDescribedNodes] = useState<DescribedNode[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [activeResult, setActiveResult] = useState<Job | null>(null);
  const [viewMode, setViewMode] = useState<"slider" | "side-by-side" | "difference">("slider");
  const [presetRefresh, setPresetRefresh] = useState(0);
  const [suggestions, setSuggestions] = useState<SuggestedPreset[]>([]);
  const [banner, setBanner] = useState<{ tone: "error" | "success"; message: string } | null>(
    null,
  );
  const [editorMode, setEditorMode] = useState<"list" | "dag">("list");
  const [dagNodes, setDagNodes] = useState<DagNode[]>([]);
  const [dagEdges, setDagEdges] = useState<DagEdge[]>([]);
  const [collapsed, setCollapsed] = useState<Record<Easel, boolean>>({
    rail: false,
    workflow: false,
    inspector: false,
  });

  const [batchIndex, setBatchIndex] = useState(0);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const batchCancelRef = useRef(false);
  const historyPast = useRef<{ stages: Stage[]; dagNodes: DagNode[]; dagEdges: DagEdge[] }[]>([]);
  const historyFuture = useRef<{ stages: Stage[]; dagNodes: DagNode[]; dagEdges: DagEdge[] }[]>([]);

  const snapshotEditor = useCallback(
    () => ({ stages, dagNodes, dagEdges }),
    [stages, dagNodes, dagEdges],
  );

  const pushHistory = useCallback(() => {
    historyPast.current.push(snapshotEditor());
    historyFuture.current = [];
    if (historyPast.current.length > 48) historyPast.current.shift();
  }, [snapshotEditor]);

  const undoEditor = useCallback(() => {
    const prev = historyPast.current.pop();
    if (!prev) return;
    historyFuture.current.push(snapshotEditor());
    setStages(prev.stages);
    setDagNodes(prev.dagNodes);
    setDagEdges(prev.dagEdges);
  }, [snapshotEditor]);

  const redoEditor = useCallback(() => {
    const next = historyFuture.current.pop();
    if (!next) return;
    historyPast.current.push(snapshotEditor());
    setStages(next.stages);
    setDagNodes(next.dagNodes);
    setDagEdges(next.dagEdges);
  }, [snapshotEditor]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redoEditor();
      else undoEditor();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undoEditor, redoEditor]);

  const downloads = useWeightDownloads();
  const jobEvents = useJobEvents(job?.id ?? null);
  const filePickerRef = useRef<HTMLInputElement>(null);
  const folderPickerRef = useRef<HTMLInputElement>(null);
  const lastHandoffToken = useRef<number | null>(null);

  const describedByType = useMemo(
    () => Object.fromEntries(describedNodes.map((n) => [n.id, n])),
    [describedNodes],
  );

  /** Canonical PipelineJson for the active editor. */
  function currentPipeline(): { pipeline: PipelineJson; error: string | null } {
    return editorMode === "dag"
      ? dagToPipeline(dagNodes, dagEdges)
      : stagesToPipeline(stages);
  }

  function applyPipeline(pipeline: PipelineJson) {
    const nextStages = pipelineToStages(pipeline, describedByType);
    setStages(nextStages);
    const { nodes, edges } = pipelineToDag(pipeline, describedByType);
    setDagNodes(nodes);
    setDagEdges(edges);
  }

  useEffect(() => {
    listNodes()
      .then(setDescribedNodes)
      .catch(() => setDescribedNodes([]));
  }, []);

  useEffect(() => {
    if (!handoff || handoff.token === lastHandoffToken.current) return;
    if (describedNodes.length === 0) return;
    lastHandoffToken.current = handoff.token;
    setFile(handoff.file);
    setImageUrl(URL.createObjectURL(handoff.file));
    applyPipeline(handoff.pipeline);
    setPipelineError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handoff, describedNodes, describedByType]);

  useEffect(() => {
    if (!file) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    autoSuggest(file)
      .then((result) => {
        if (!cancelled) setSuggestions(result.suggestions);
      })
      .catch(() => {
        if (!cancelled) setSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [file]);

  useEffect(() => {
    if (!banner) return;
    const timer = setTimeout(() => setBanner(null), 4500);
    return () => clearTimeout(timer);
  }, [banner]);

  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [imageUrl]);

  useEffect(() => {
    if (!job) return;
    setStages((current) =>
      current.map((s) => {
        const event = jobEvents.byNode[s.id];
        if (!event) return s;
        return {
          ...s,
          runStatus: event.status,
          runProgress: event.progress,
          previewUrl: event.preview_url ?? s.previewUrl ?? null,
          cached: event.cached,
        };
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobEvents.byNode, job]);

  useEffect(() => {
    if (jobEvents.connectionLost && running) {
      setRunning(false);
      setBanner({ tone: "error", message: t("studio.connectionLost") });
    }
  }, [jobEvents.connectionLost, running, t]);

  useEffect(() => {
    if (!jobEvents.terminal || !job) return;
    getJob(job.id)
      .then((updated) => {
        setJob(updated);
        setRunning(false);
        setRuns((prev) => prev.map((r) => (r.job.id === updated.id ? { job: updated } : r)));
        if (updated.state === "done") {
          setActiveResult(updated);
        } else if (updated.state === "error") {
          setBanner({ tone: "error", message: updated.error ?? t("simple.stage.error") });
        } else if (updated.state === "cancelled") {
          setBanner({ tone: "error", message: t("simple.stage.cancelled") });
        }
        if (updated.events_truncated) {
          setBanner({ tone: "error", message: t("studio.eventsTruncated") });
        }
      })
      .catch((err) => {
        setRunning(false);
        setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobEvents.terminal]);

  const selectedStage = useMemo(() => {
    if (editorMode === "dag") {
      const n = dagNodes.find((s) => s.id === selectedId);
      if (!n) return null;
      return {
        id: n.id,
        nodeType: n.nodeType,
        displayName: n.displayName,
        category: n.category,
        params: n.params,
        pinned: n.pinned,
      } as Stage;
    }
    return stages.find((s) => s.id === selectedId) ?? null;
  }, [stages, dagNodes, selectedId, editorMode]);
  const selectedDescribed = selectedStage ? (describedByType[selectedStage.nodeType] ?? null) : null;

  const switchEditorMode = useCallback(
    (mode: "list" | "dag") => {
      if (mode === editorMode) return;
      if (mode === "dag") {
        const { pipeline, error } = stagesToPipeline(stages);
        if (error) {
          setBanner({ tone: "error", message: error });
          return;
        }
        const { nodes, edges } = pipelineToDag(pipeline, describedByType);
        setDagNodes(nodes);
        setDagEdges(edges);
      } else {
        const { pipeline, error } = dagToPipeline(dagNodes, dagEdges);
        if (error) {
          setBanner({ tone: "error", message: error });
          return;
        }
        setStages(pipelineToStages(pipeline, describedByType));
      }
      setEditorMode(mode);
    },
    [editorMode, stages, dagNodes, dagEdges, describedByType],
  );

  const onAddStage = useCallback(
    (nodeTypeId: string) => {
      pushHistory();
      const described = describedByType[nodeTypeId];
      if (!described) return;
      if (editorMode === "dag") {
        const node = createDagNode(described, 80 + dagNodes.length * 40, 80);
        setDagNodes((prev) => [...prev, node]);
        setSelectedId(node.id);
      } else {
        const stage = createStage(described);
        setStages((prev) => [...prev, stage]);
        setSelectedId(stage.id);
      }
      setPipelineError(null);
    },
    [describedByType, editorMode, dagNodes.length, pushHistory],
  );

  const onMoveStage = useCallback(
    (stageId: string, direction: -1 | 1) => {
      pushHistory();
      setStages((prev) => {
        const index = prev.findIndex((s) => s.id === stageId);
        const target = index + direction;
        if (index < 0 || target < 0 || target >= prev.length) return prev;
        const next = [...prev];
        [next[index], next[target]] = [next[target]!, next[index]!];
        return next;
      });
    },
    [pushHistory],
  );

  const onRemoveStage = useCallback(
    (stageId: string) => {
      pushHistory();
      setStages((prev) => prev.filter((s) => s.id !== stageId));
      if (selectedId === stageId) setSelectedId(null);
    },
    [selectedId, pushHistory],
  );

  const onAutoOrder = useCallback(() => {
    if (stages.length < 2) return;
    pushHistory();
    const params: Record<string, Record<string, unknown>> = {};
    for (const s of stages) params[s.nodeType] = s.params;
    autoOrderPipeline(
      stages.map((s) => s.nodeType),
      params,
    )
      .then((pipeline) => {
        applyPipeline(pipeline);
        setPipelineError(null);
      })
      .catch((err) =>
        setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stages, describedByType, pushHistory]);

  const onParamsChange = useCallback(
    (stageId: string, params: Record<string, unknown>) => {
      if (editorMode === "dag") {
        setDagNodes((prev) => prev.map((n) => (n.id === stageId ? { ...n, params } : n)));
      } else {
        setStages((prev) => prev.map((s) => (s.id === stageId ? { ...s, params } : s)));
      }
    },
    [editorMode],
  );

  const onPinnedChange = useCallback(
    (stageId: string, pinned: boolean) => {
      if (editorMode === "dag") {
        setDagNodes((prev) => prev.map((n) => (n.id === stageId ? { ...n, pinned } : n)));
      } else {
        setStages((prev) => prev.map((s) => (s.id === stageId ? { ...s, pinned } : s)));
      }
    },
    [editorMode],
  );

  const onAcknowledge = useCallback((nodeId: string) => {
    acknowledgeLicense(nodeId)
      .then((status) => {
        setDescribedNodes((list) => list.map((n) => (n.id === nodeId ? { ...n, weights: status } : n)));
      })
      .catch((err) =>
        setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }),
      );
  }, []);

  const onWeightsChanged = useCallback(() => {
    if (!selectedStage) return;
    getNode(selectedStage.nodeType)
      .then((updated) => {
        setDescribedNodes((list) => list.map((n) => (n.id === updated.id ? updated : n)));
      })
      .catch(() => {});
  }, [selectedStage]);

  function pickPhoto(selected: File) {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    setFile(selected);
    setImageUrl(URL.createObjectURL(selected));
    setActiveResult(null);
  }

  async function ensureWeights(pipeline: PipelineJson): Promise<boolean> {
    const missing = missingWeightsFor(pipeline, describedByType);
    if (missing.length === 0) return true;
    setBanner({
      tone: "success",
      message: t("studio.batch.preflight", { count: missing.length }),
    });
    const ok = await downloads.downloadAll(missing);
    if (!ok) {
      setBanner({
        tone: "error",
        message: t("studio.batch.missingWeights", {
          nodes: missing.map((id) => describedByType[id]?.display_name ?? id).join(", "),
        }),
      });
      return false;
    }
    setDescribedNodes(await listNodes());
    return true;
  }

  async function handleRun(): Promise<void> {
    if (batchFiles.length > 0) {
      await handleBatchRun();
      return;
    }
    if (!file) return;
    const { pipeline, error } = currentPipeline();
    if (error) {
      setBanner({ tone: "error", message: error });
      return;
    }
    if (pipeline.nodes.length === 0) {
      setBanner({ tone: "error", message: t("pipeline.stages.empty") });
      return;
    }
    setRunning(true);
    setBanner(null);
    batchCancelRef.current = false;
    try {
      if (!(await ensureWeights(pipeline))) {
        setRunning(false);
        return;
      }
      const submitted = await submitJob(file, { pipeline });
      setJob(submitted);
      setRuns((prev) => [{ job: submitted }, ...prev].slice(0, 24));
    } catch (err) {
      setRunning(false);
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  async function handleBatchRun(): Promise<void> {
    const { pipeline, error } = currentPipeline();
    if (error || pipeline.nodes.length === 0) {
      setBanner({ tone: "error", message: error ?? t("pipeline.stages.empty") });
      return;
    }
    setRunning(true);
    setBatchTotal(batchFiles.length);
    setBanner(null);
    batchCancelRef.current = false;
    try {
      if (!(await ensureWeights(pipeline))) {
        setRunning(false);
        setBatchTotal(0);
        return;
      }
      let completed = 0;
      for (let i = 0; i < batchFiles.length; i++) {
        if (batchCancelRef.current) break;
        setBatchIndex(i + 1);
        const batchFile = batchFiles[i]!;
        pickPhoto(batchFile);
        const submitted = await submitJob(batchFile, { pipeline });
        setJob(submitted);
        setRuns((prev) => [{ job: submitted }, ...prev].slice(0, 24));
        const finished = await waitForJobDone(submitted.id, () => batchCancelRef.current);
        setJob(finished);
        setRuns((prev) => prev.map((r) => (r.job.id === finished.id ? { job: finished } : r)));
        if (finished.state === "done") {
          setActiveResult(finished);
          completed += 1;
        } else if (finished.state === "cancelled" || batchCancelRef.current) {
          setBanner({
            tone: "error",
            message: t("studio.batch.cancelled", {
              current: i + 1,
              total: batchFiles.length,
            }),
          });
          break;
        } else {
          setBanner({ tone: "error", message: finished.error ?? t("simple.stage.error") });
          break;
        }
      }
      if (!batchCancelRef.current && completed === batchFiles.length) {
        setBanner({ tone: "success", message: t("studio.batch.done", { count: completed }) });
      }
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    } finally {
      setRunning(false);
      setBatchIndex(0);
      setBatchTotal(0);
    }
  }

  function handleFork(recalledJob: Job) {
    applyPipeline(recalledJob.pipeline);
    setSelectedId(null);
    setPipelineError(null);
    if (recalledJob.state === "done") setActiveResult(recalledJob);
  }

  async function handleSavePreset(name: string) {
    const { pipeline, error } = currentPipeline();
    if (error) {
      setBanner({ tone: "error", message: error });
      return;
    }
    try {
      await savePreset(name, pipeline);
      setPresetRefresh((v) => v + 1);
      setBanner({ tone: "success", message: t("studio.presets.saved", { name }) });
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  async function handleLoadPreset(name: string) {
    try {
      const preset = await getPreset(name);
      pushHistory();
      applyPipeline(preset.pipeline);
      setSelectedId(null);
      setPipelineError(null);
      try {
        const lib = await listInstructirPrompts();
        const match = lib.presets.find((p) => p.pairs_with_workflow?.includes(name));
        if (match) {
          setBanner({
            tone: "success",
            message: t("studio.presets.suggestedPrompt", { title: match.title }),
          });
          setStages((current) => {
            const hasMaster = current.some((s) => s.nodeType === "instructir");
            if (!hasMaster) return current;
            return current.map((s) =>
              s.nodeType === "instructir"
                ? {
                    ...s,
                    params: {
                      ...s.params,
                      prompt_preset: match.id,
                      instruction: match.instruction,
                    },
                  }
                : s,
            );
          });
        }
      } catch {
        /* optional suggestion */
      }
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  async function handleBuildEnsemble(params: Record<string, unknown>) {
    try {
      pushHistory();
      const plan = await buildGuidedEnsemble({
        prompt_preset_id: String(params.prompt_preset ?? "") || null,
        instruction: String(params.instruction ?? "") || null,
        mode: String(params.mode ?? "guide_and_finish"),
        image: file ?? null,
      });
      applyPipeline(plan.pipeline);
      setSelectedId(null);
      setBanner({
        tone: "success",
        message: `${t("studio.ensemble.built")} — ${t("studio.ensemble.preview", {
          count: plan.chain.length,
          chain: plan.chain.map((id) => describedByType[id]?.display_name ?? id).join(" → "),
        })}`,
      });
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  function handleImportWorkflow(importFile: File) {
    const reader = new FileReader();
    reader.onload = () => {
      importWorkflowText(String(reader.result))
        .then((pipeline) => {
          pushHistory();
          applyPipeline(pipeline);
          setSelectedId(null);
          setPipelineError(null);
        })
        .catch((err) =>
          setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }),
        );
    };
    reader.readAsText(importFile);
  }

  function handleExportWorkflow() {
    const { pipeline, error } = currentPipeline();
    if (error) {
      setBanner({ tone: "error", message: error });
      return;
    }
    exportWorkflowText(pipeline)
      .then(({ text }) => {
        const blob = new Blob([text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "workflow.txt";
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch((err) =>
        setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }),
      );
  }

  function downloadResult(filename: string) {
    if (!activeResult) return;
    const a = document.createElement("a");
    a.href = jobResultUrl(activeResult.id);
    a.download = filename;
    a.click();
  }

  const commands = useMemo(
    () => [
      {
        id: "studio.run",
        label: t("studio.canvas.run"),
        category: "Studio Mode",
        icon: "play" as const,
        run: (): void => {
          void handleRun();
        },
      },
      {
        id: "studio.attach-photo",
        label: t("studio.attachPhoto"),
        category: "Studio Mode",
        icon: "image" as const,
        run: () => filePickerRef.current?.click(),
      },
      {
        id: "studio.export-workflow",
        label: t("studio.presets.export"),
        category: "Studio Mode",
        icon: "export" as const,
        run: handleExportWorkflow,
      },
      {
        id: "studio.auto-order",
        label: t("pipeline.stages.autoOrder"),
        category: "Studio Mode",
        icon: "sort" as const,
        run: onAutoOrder,
      },
      {
        id: "studio.undo",
        label: t("studio.undo"),
        category: "Studio Mode",
        shortcut: "Ctrl+Z",
        run: undoEditor,
      },
      {
        id: "studio.redo",
        label: t("studio.redo"),
        category: "Studio Mode",
        shortcut: "Ctrl+Shift+Z",
        run: redoEditor,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [file, stages, dagNodes, dagEdges, editorMode],
  );
  useRegisterCommands("studio-mode", commands);

  function toggleEasel(key: Easel) {
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className={styles.screen}>
      <PresetBar
        onSave={handleSavePreset}
        onLoad={handleLoadPreset}
        onImport={handleImportWorkflow}
        onExport={handleExportWorkflow}
        onLoadSuggestion={(pipeline, name) => {
          pushHistory();
          applyPipeline(pipeline);
          setSelectedId(null);
          setPipelineError(null);
          setBanner({
            tone: "success",
            message: t("studio.presets.suggestedPrompt", { title: name }),
          });
        }}
        refreshToken={presetRefresh}
        suggestions={suggestions}
      />

      <div className={styles.toolbarRow}>
        <div className={styles.toolbarGroup}>
          {file ? (
            <div className={styles.photoChip}>
              {imageUrl && <img src={imageUrl} alt="" />}
              <span title={file.name}>{file.name}</span>
              <Button variant="ghost" size="small" onClick={() => filePickerRef.current?.click()}>
                {t("studio.changePhoto")}
              </Button>
            </div>
          ) : (
            <Button variant="secondary" icon="image" onClick={() => filePickerRef.current?.click()}>
              {t("studio.attachPhoto")}
            </Button>
          )}
          <input
            ref={filePickerRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
            className="visually-hidden"
            aria-label={t("studio.attachPhoto")}
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) pickPhoto(selected);
              e.target.value = "";
            }}
          />
          <Button variant="ghost" size="small" onClick={() => folderPickerRef.current?.click()}>
            {t("studio.batch.folder")}
          </Button>
          <input
            ref={folderPickerRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
            className="visually-hidden"
            aria-label={t("studio.batch.folder")}
            multiple
            // @ts-expect-error webkitdirectory is non-standard but widely supported
            webkitdirectory=""
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []).filter((f) =>
                /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(f.name),
              );
              if (files.length > 0) {
                setBatchFiles(files);
                pickPhoto(files[0]!);
              }
              e.target.value = "";
            }}
          />
        </div>
        <div className={styles.spacer} />
        <div className={styles.toolbarGroup}>
          <div className={styles.easelToggles} role="toolbar" aria-label={t("studio.editor.mode")}>
            <button
              type="button"
              className={styles.easelBtn}
              aria-pressed={!collapsed.rail}
              onClick={() => toggleEasel("rail")}
            >
              {collapsed.rail ? t("studio.rail.expand") : t("studio.rail.collapse")}
            </button>
            <button
              type="button"
              className={styles.easelBtn}
              aria-pressed={!collapsed.workflow}
              onClick={() => toggleEasel("workflow")}
            >
              {collapsed.workflow ? t("studio.workflow.expand") : t("studio.workflow.collapse")}
            </button>
            <button
              type="button"
              className={styles.easelBtn}
              aria-pressed={!collapsed.inspector}
              onClick={() => toggleEasel("inspector")}
            >
              {collapsed.inspector ? t("studio.inspector.expand") : t("studio.inspector.collapse")}
            </button>
          </div>
          <div className={styles.editorToggle} role="tablist" aria-label={t("studio.editor.mode")}>
            <button
              type="button"
              role="tab"
              aria-selected={editorMode === "list"}
              className={editorMode === "list" ? styles.modeActive : styles.modeTab}
              onClick={() => switchEditorMode("list")}
            >
              {t("studio.editor.list")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={editorMode === "dag"}
              className={editorMode === "dag" ? styles.modeActive : styles.modeTab}
              onClick={() => switchEditorMode("dag")}
            >
              {t("studio.editor.dag")}
            </button>
          </div>
          <Button
            variant="ghost"
            size="small"
            title={t("studio.editor.dualFace")}
            onClick={() => {
              const tpl = dualFaceBlendTemplate(describedByType);
              if (!tpl) return;
              pushHistory();
              setEditorMode("dag");
              setDagNodes(tpl.nodes);
              setDagEdges(tpl.edges);
            }}
          >
            {t("studio.editor.dualFace")}
          </Button>
          <Button
            variant="primary"
            icon="play"
            className={styles.stickyRun}
            onClick={() => void handleRun()}
            disabled={(!file && batchFiles.length === 0) || running}
            aria-label={t("a11y.stickyRun")}
          >
            {running ? t("studio.canvas.running") : t("studio.canvas.run")}
          </Button>
          {running && job && (
            <Button
              variant="ghost"
              size="small"
              onClick={() => {
                batchCancelRef.current = true;
                void cancelJob(job.id);
              }}
            >
              {t("studio.cancelRun")}
            </Button>
          )}
        </div>
        {batchTotal > 0 && (
          <StatusLine
            message={t("studio.batch.progress", { current: batchIndex, total: batchTotal })}
          />
        )}
        {banner && (
          <StatusLine
            message={banner.message}
            tone={banner.tone === "error" ? "error" : "success"}
          />
        )}
      </div>

      <div className={styles.body}>
        {!collapsed.rail && (
          <div className={styles.easelRail}>
            <ModelStackRail nodes={describedNodes} onAddNode={onAddStage} />
          </div>
        )}
        {!collapsed.workflow && (
          <div className={styles.easelWorkflow}>
            {editorMode === "list" ? (
              <StageList
                stages={stages}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onMove={onMoveStage}
                onRemove={onRemoveStage}
                onAutoOrder={onAutoOrder}
                error={pipelineError}
              />
            ) : (
              <PipelineCanvas
                nodes={dagNodes}
                edges={dagEdges}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onMoveNode={(id, x, y) =>
                  setDagNodes((prev) => prev.map((n) => (n.id === id ? { ...n, x, y } : n)))
                }
                onConnect={(from, to, toInput) => {
                  pushHistory();
                  setDagEdges((prev) => [
                    ...prev,
                    { id: `e${prev.length}`, from, to, toInput },
                  ]);
                }}
                onRemoveNode={(id) => {
                  pushHistory();
                  setDagNodes((prev) => prev.filter((n) => n.id !== id));
                  setDagEdges((prev) => prev.filter((e) => e.from !== id && e.to !== id));
                  if (selectedId === id) setSelectedId(null);
                }}
              />
            )}
          </div>
        )}
        {!collapsed.inspector && (
          <div className={styles.easelInspector}>
            <Inspector
              selectedStage={selectedStage}
              described={selectedDescribed}
              onParamsChange={onParamsChange}
              onPinnedChange={onPinnedChange}
              downloads={downloads}
              onAcknowledge={onAcknowledge}
              onWeightsChanged={onWeightsChanged}
              onBuildEnsemble={(params) => void handleBuildEnsemble(params)}
            />
          </div>
        )}
      </div>

      {activeResult && imageUrl && activeResult.state === "done" && (
        <section className={styles.resultPane} aria-label={t("studio.result.title")}>
          <LightTable
            beforeUrl={imageUrl}
            afterUrl={jobResultUrl(activeResult.id)}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            reveal
          />
          <ActionBar
            onSave={() => downloadResult("restored.png")}
            onExport={() =>
              downloadResult(`${file?.name.replace(/\.[^.]+$/, "") ?? "photo"}-restored.png`)
            }
            onReset={() => setActiveResult(null)}
            onTryAgain={() => void handleRun()}
          />
        </section>
      )}

      <ContactSheet
        runs={runs}
        onFork={handleFork}
        onOpen={(j) => {
          if (j.state === "done") setActiveResult(j);
        }}
      />
    </div>
  );
}

