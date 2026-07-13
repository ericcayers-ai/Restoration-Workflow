/*
 * Studio Mode (UI_DESIGN.md section 8, ROADMAP.md Phase 3) — every choice
 * Simple Mode made, made visible and editable, plus the power to build any
 * pipeline the full model stack supports. This used to be a node-graph
 * canvas; it is now a straightforward ordered stage list (lib/pipelineStages)
 * because the vast majority of restoration pipelines are linear chains, and a
 * list a user can reorder with two buttons is easier to reason about than a
 * DAG editor for that common case. The one documented exception (LaMa's mask
 * input) is handled by pipelineStages.ts, not by this component. One engine,
 * two modes (ROADMAP.md vision): this screen submits the exact same
 * PipelineJson the executor and the CLI accept.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  acknowledgeLicense,
  autoOrderPipeline,
  exportWorkflowText,
  getJob,
  getNode,
  getPreset,
  importWorkflowText,
  listNodes,
  savePreset,
  submitJob,
} from "../../lib/api";
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
import type { DescribedNode, Job, PipelineJson } from "../../lib/types";
import { useJobEvents } from "../../lib/useJobEvents";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "../common/Button";
import { StatusLine } from "../common/StatusLine";
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
  const [presetRefresh, setPresetRefresh] = useState(0);
  const [banner, setBanner] = useState<{ tone: "error" | "success"; message: string } | null>(
    null,
  );
  const [editorMode, setEditorMode] = useState<"list" | "dag">("list");
  const [dagNodes, setDagNodes] = useState<DagNode[]>([]);
  const [dagEdges, setDagEdges] = useState<DagEdge[]>([]);

  const [batchIndex, setBatchIndex] = useState(0);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
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

  useEffect(() => {
    listNodes()
      .then(setDescribedNodes)
      .catch(() => setDescribedNodes([]));
  }, []);

  // "Open in Studio" handoff (UI_DESIGN.md section 7): waits for the node
  // catalog so pipelineToStages can resolve real display names/categories
  // instead of falling back to raw ids.
  useEffect(() => {
    if (!handoff || handoff.token === lastHandoffToken.current) return;
    if (describedNodes.length === 0) return;
    lastHandoffToken.current = handoff.token;
    setFile(handoff.file);
    setImageUrl(URL.createObjectURL(handoff.file));
    setStages(pipelineToStages(handoff.pipeline, describedByType));
    setPipelineError(null);
  }, [handoff, describedNodes, describedByType]);

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

  // Live per-stage status into the list — one WebSocket, one source of truth,
  // feeding both Simple Mode's status line and this progress fill
  // (ARCHITECTURE.md section 2).
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
    if (!jobEvents.terminal || !job) return;
    getJob(job.id)
      .then((updated) => {
        setJob(updated);
        setRunning(false);
        setRuns((prev) => prev.map((r) => (r.job.id === updated.id ? { job: updated } : r)));
        if (updated.state === "error") {
          setBanner({ tone: "error", message: updated.error ?? "Run failed" });
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
    [describedByType, editorMode, dagNodes.length],
  );

  const onMoveStage = useCallback((stageId: string, direction: -1 | 1) => {
    setStages((prev) => {
      const index = prev.findIndex((s) => s.id === stageId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target]!, next[index]!];
      return next;
    });
  }, []);

  const onRemoveStage = useCallback(
    (stageId: string) => {
      setStages((prev) => prev.filter((s) => s.id !== stageId));
      if (selectedId === stageId) setSelectedId(null);
    },
    [selectedId],
  );

  const onAutoOrder = useCallback(() => {
    if (stages.length < 2) return;
    const params: Record<string, Record<string, unknown>> = {};
    for (const s of stages) params[s.nodeType] = s.params;
    autoOrderPipeline(
      stages.map((s) => s.nodeType),
      params,
    )
      .then((pipeline) => {
        setStages(pipelineToStages(pipeline, describedByType));
        setPipelineError(null);
      })
      .catch((err) => setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }));
  }, [stages, describedByType]);

  const onParamsChange = useCallback((stageId: string, params: Record<string, unknown>) => {
    setStages((prev) => prev.map((s) => (s.id === stageId ? { ...s, params } : s)));
  }, []);

  const onPinnedChange = useCallback((stageId: string, pinned: boolean) => {
    setStages((prev) => prev.map((s) => (s.id === stageId ? { ...s, pinned } : s)));
  }, []);

  const onAcknowledge = useCallback((nodeId: string) => {
    acknowledgeLicense(nodeId)
      .then((status) => {
        setDescribedNodes((list) => list.map((n) => (n.id === nodeId ? { ...n, weights: status } : n)));
      })
      .catch((err) => setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }));
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
  }

  async function handleRun(): Promise<void> {
    if (batchFiles.length > 0) {
      await handleBatchRun();
      return;
    }
    if (!file) return;
    const { pipeline, error } =
      editorMode === "dag"
        ? dagToPipeline(dagNodes, dagEdges)
        : stagesToPipeline(stages);
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
    try {
      const submitted = await submitJob(file, { pipeline });
      setJob(submitted);
      setRuns((prev) => [{ job: submitted }, ...prev].slice(0, 24));
    } catch (err) {
      setRunning(false);
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  async function handleBatchRun(): Promise<void> {
    const { pipeline, error } =
      editorMode === "dag"
        ? dagToPipeline(dagNodes, dagEdges)
        : stagesToPipeline(stages);
    if (error || pipeline.nodes.length === 0) {
      setBanner({ tone: "error", message: error ?? t("pipeline.stages.empty") });
      return;
    }
    setRunning(true);
    setBatchTotal(batchFiles.length);
    setBanner(null);
    try {
      for (let i = 0; i < batchFiles.length; i++) {
        setBatchIndex(i + 1);
        const batchFile = batchFiles[i]!;
        const submitted = await submitJob(batchFile, { pipeline });
        setJob(submitted);
        setRuns((prev) => [{ job: submitted }, ...prev].slice(0, 24));
      }
      setBanner({ tone: "success", message: t("studio.batch.done", { count: batchFiles.length }) });
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    } finally {
      setRunning(false);
      setBatchIndex(0);
      setBatchTotal(0);
    }
  }

  function handleFork(recalledJob: Job) {
    setStages(pipelineToStages(recalledJob.pipeline, describedByType));
    setSelectedId(null);
    setPipelineError(null);
  }

  async function handleSavePreset(name: string) {
    const { pipeline, error } = stagesToPipeline(stages);
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
      setStages(pipelineToStages(preset.pipeline, describedByType));
      setSelectedId(null);
      setPipelineError(null);
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  function handleImportWorkflow(importFile: File) {
    const reader = new FileReader();
    reader.onload = () => {
      importWorkflowText(String(reader.result))
        .then((pipeline) => {
          setStages(pipelineToStages(pipeline, describedByType));
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
    const { pipeline, error } = stagesToPipeline(stages);
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
      .catch((err) => setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }));
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
    [file, stages],
  );
  useRegisterCommands("studio-mode", commands);

  return (
    <div className={styles.screen}>
      <PresetBar
        onSave={handleSavePreset}
        onLoad={handleLoadPreset}
        onImport={handleImportWorkflow}
        onExport={handleExportWorkflow}
        refreshToken={presetRefresh}
      />

      <div className={styles.toolbarRow}>
        {file ? (
          <div className={styles.photoChip}>
            {imageUrl && <img src={imageUrl} alt="" />}
            <span>{file.name}</span>
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
          onChange={(e) => {
            const selected = e.target.files?.[0];
            if (selected) pickPhoto(selected);
            e.target.value = "";
          }}
        />
        <Button variant="secondary" onClick={() => folderPickerRef.current?.click()}>
          {t("studio.batch.folder")}
        </Button>
        <input
          ref={folderPickerRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
          className="visually-hidden"
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
        <div className={styles.spacer} />
        <div className={styles.editorToggle} role="tablist" aria-label="Editor mode">
          <button
            type="button"
            role="tab"
            aria-selected={editorMode === "list"}
            className={editorMode === "list" ? styles.modeActive : styles.modeTab}
            onClick={() => setEditorMode("list")}
          >
            {t("studio.editor.list")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={editorMode === "dag"}
            className={editorMode === "dag" ? styles.modeActive : styles.modeTab}
            onClick={() => {
              setEditorMode("dag");
              const { nodes, edges } = pipelineToDag(
                stagesToPipeline(stages).pipeline,
                describedByType,
              );
              setDagNodes(nodes);
              setDagEdges(edges);
            }}
          >
            {t("studio.editor.dag")}
          </button>
        </div>
        <Button
          variant="ghost"
          size="small"
          onClick={() => {
            const tpl = dualFaceBlendTemplate(describedByType);
            if (!tpl) return;
            setEditorMode("dag");
            setDagNodes(tpl.nodes);
            setDagEdges(tpl.edges);
          }}
        >
          {t("studio.editor.dualFace")}
        </Button>
        <div className={styles.spacer} />
        <Button
          variant="primary"
          icon="play"
          onClick={() => void handleRun()}
          disabled={(!file && batchFiles.length === 0) || running}
        >
          {running ? t("studio.canvas.running") : t("studio.canvas.run")}
        </Button>
        {batchTotal > 0 && (
          <StatusLine message={t("studio.batch.progress", { current: batchIndex, total: batchTotal })} />
        )}
        {banner && (
          <StatusLine
            message={banner.message}
            tone={banner.tone === "error" ? "error" : "success"}
          />
        )}
      </div>

      <div className={styles.body}>
        <ModelStackRail nodes={describedNodes} onAddNode={onAddStage} />
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
            onConnect={(from, to, toInput) =>
              setDagEdges((prev) => [
                ...prev,
                { id: `e${prev.length}`, from, to, toInput },
              ])
            }
            onRemoveNode={(id) => {
              setDagNodes((prev) => prev.filter((n) => n.id !== id));
              setDagEdges((prev) => prev.filter((e) => e.from !== id && e.to !== id));
            }}
          />
        )}
        <Inspector
          selectedStage={selectedStage}
          described={selectedDescribed}
          onParamsChange={onParamsChange}
          onPinnedChange={onPinnedChange}
          downloads={downloads}
          onAcknowledge={onAcknowledge}
          onWeightsChanged={onWeightsChanged}
        />
      </div>

      <ContactSheet runs={runs} onFork={handleFork} />
    </div>
  );
}
