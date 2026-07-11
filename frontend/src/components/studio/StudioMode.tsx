/*
 * Studio Mode (UI_DESIGN.md section 8, ROADMAP.md Phase 3) — every choice
 * Simple Mode made, made visible and editable, plus real DAG authoring power
 * Simple Mode never needs. One engine, two modes (ROADMAP.md vision): this
 * screen submits the exact same PipelineJson the executor and the CLI accept.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { addEdge, useEdgesState, useNodesState, type OnConnect } from "@xyflow/react";
import {
  ApiError,
  acknowledgeLicense,
  getJob,
  getNode,
  getPreset,
  listNodes,
  savePreset,
  submitJob,
} from "../../lib/api";
import {
  PRIMARY_HANDLE,
  createNode,
  flowToPipeline,
  pipelineToFlow,
  sinkNodeId,
  type RFEdge,
  type RFNode,
} from "../../lib/canvasPipeline";
import { useRegisterCommands } from "../../lib/commands";
import { useT } from "../../lib/i18n";
import type { DescribedNode, Job, PipelineJson } from "../../lib/types";
import { useJobEvents } from "../../lib/useJobEvents";
import { useWeightDownloads } from "../../lib/useWeightDownloads";
import { Button } from "../common/Button";
import { StatusLine } from "../common/StatusLine";
import { Canvas } from "./Canvas";
import { ContactSheet, type RunRecord } from "./ContactSheet";
import { Inspector } from "./Inspector";
import { ModelStackRail } from "./ModelStackRail";
import { PresetBar } from "./PresetBar";
import styles from "./StudioMode.module.css";

export interface StudioHandoff {
  pipeline: PipelineJson;
  file: File;
  token: number;
}

export function StudioMode({ handoff }: { handoff: StudioHandoff | null }) {
  const t = useT();
  const [describedNodes, setDescribedNodes] = useState<DescribedNode[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<RFNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<RFEdge>([]);
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [presetRefresh, setPresetRefresh] = useState(0);
  const [banner, setBanner] = useState<{ tone: "error" | "success"; message: string } | null>(
    null,
  );

  const downloads = useWeightDownloads();
  const jobEvents = useJobEvents(job?.id ?? null);
  const filePickerRef = useRef<HTMLInputElement>(null);
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
  // catalog so pipelineToFlow can resolve real display names/categories
  // instead of falling back to raw ids.
  useEffect(() => {
    if (!handoff || handoff.token === lastHandoffToken.current) return;
    if (describedNodes.length === 0) return;
    lastHandoffToken.current = handoff.token;
    setFile(handoff.file);
    setImageUrl(URL.createObjectURL(handoff.file));
    const { nodes: n, edges: e } = pipelineToFlow(handoff.pipeline, describedByType);
    setNodes(n);
    setEdges(e);
  }, [handoff, describedNodes, describedByType, setNodes, setEdges]);

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

  // Live per-node status onto the canvas — one WebSocket, one source of
  // truth, feeding both Simple Mode's status line and this progress fill
  // (ARCHITECTURE.md section 2).
  useEffect(() => {
    if (!job) return;
    setNodes((current) =>
      current.map((n) => {
        const event = jobEvents.byNode[n.id];
        if (!event) return n;
        return {
          ...n,
          data: {
            ...n.data,
            runStatus: event.status,
            runProgress: event.progress,
            previewUrl: event.preview_url ?? n.data.previewUrl ?? null,
            cached: event.cached,
          },
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

  const selectedNode = useMemo(() => nodes.find((n) => n.selected) ?? null, [nodes]);
  const selectedDescribed = selectedNode ? (describedByType[selectedNode.data.nodeType] ?? null) : null;

  const onConnect = useCallback<OnConnect>(
    (connection) => {
      if (connection.source === connection.target) return;
      setEdges((eds) => {
        const targetHandle = connection.targetHandle ?? PRIMARY_HANDLE;
        const withoutConflict = eds.filter(
          (e) => !(e.target === connection.target && (e.targetHandle ?? PRIMARY_HANDLE) === targetHandle),
        );
        return addEdge(connection, withoutConflict);
      });
    },
    [setEdges],
  );

  const placeNode = useCallback(
    (nodeTypeId: string, position: { x: number; y: number }) => {
      const described = describedByType[nodeTypeId];
      if (!described) return;
      setNodes((nds) => [...nds, createNode(described, position)]);
    },
    [describedByType, setNodes],
  );

  const onAddNode = useCallback(
    (nodeTypeId: string) => {
      // Lay clicked-in nodes out left-to-right in the reading order a chain is
      // usually built in, wrapping to a second row — a node card is 220px wide,
      // so the column step has to clear that or cards land on top of each other.
      const index = nodes.length;
      const col = index % 4;
      const row = Math.floor(index / 4);
      placeNode(nodeTypeId, { x: 40 + col * 250, y: 40 + row * 150 });
    },
    [nodes.length, placeNode],
  );

  const onParamsChange = useCallback(
    (nodeId: string, params: Record<string, unknown>) => {
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, params } } : n)));
    },
    [setNodes],
  );

  const onPinnedChange = useCallback(
    (nodeId: string, pinned: boolean) => {
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, pinned } } : n)));
    },
    [setNodes],
  );

  const onAcknowledge = useCallback((nodeId: string) => {
    acknowledgeLicense(nodeId)
      .then((status) => {
        setDescribedNodes((list) => list.map((n) => (n.id === nodeId ? { ...n, weights: status } : n)));
      })
      .catch((err) => setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) }));
  }, []);

  const onWeightsChanged = useCallback(() => {
    if (!selectedNode) return;
    getNode(selectedNode.data.nodeType)
      .then((updated) => {
        setDescribedNodes((list) => list.map((n) => (n.id === updated.id ? updated : n)));
      })
      .catch(() => {});
  }, [selectedNode]);

  function pickPhoto(selected: File) {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    setFile(selected);
    setImageUrl(URL.createObjectURL(selected));
  }

  async function handleRun(): Promise<void> {
    if (!file) return;
    const sink = sinkNodeId(nodes, edges);
    if (!sink) {
      setBanner({ tone: "error", message: "The pipeline needs exactly one node with no outgoing connection." });
      return;
    }
    setRunning(true);
    setBanner(null);
    try {
      const pipeline = flowToPipeline(nodes, edges);
      const submitted = await submitJob(file, { pipeline });
      setJob(submitted);
      setRuns((prev) => [{ job: submitted }, ...prev].slice(0, 24));
    } catch (err) {
      setRunning(false);
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  function handleFork(recalledJob: Job) {
    const { nodes: n, edges: e } = pipelineToFlow(recalledJob.pipeline, describedByType);
    setNodes(n);
    setEdges(e);
  }

  async function handleSavePreset(name: string) {
    try {
      await savePreset(name, flowToPipeline(nodes, edges));
      setPresetRefresh((v) => v + 1);
      setBanner({ tone: "success", message: t("studio.presets.saved", { name }) });
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  async function handleLoadPreset(name: string) {
    try {
      const preset = await getPreset(name);
      const { nodes: n, edges: e } = pipelineToFlow(preset.pipeline, describedByType);
      setNodes(n);
      setEdges(e);
    } catch (err) {
      setBanner({ tone: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }

  function handleImportPreset(importFile: File) {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(String(reader.result));
        const pipeline: PipelineJson = "pipeline" in data ? data.pipeline : data;
        const { nodes: n, edges: e } = pipelineToFlow(pipeline, describedByType);
        setNodes(n);
        setEdges(e);
      } catch {
        setBanner({ tone: "error", message: `${importFile.name} is not valid pipeline JSON` });
      }
    };
    reader.readAsText(importFile);
  }

  function handleExportPreset() {
    const pipeline = flowToPipeline(nodes, edges);
    const blob = new Blob([JSON.stringify(pipeline, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pipeline.json";
    a.click();
    URL.revokeObjectURL(url);
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
        id: "studio.export-preset",
        label: t("studio.presets.export"),
        category: "Studio Mode",
        icon: "export" as const,
        run: handleExportPreset,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [file, nodes, edges],
  );
  useRegisterCommands("studio-mode", commands);

  return (
    <div className={styles.screen}>
      <PresetBar
        onSave={handleSavePreset}
        onLoad={handleLoadPreset}
        onImport={handleImportPreset}
        onExport={handleExportPreset}
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
        {banner && (
          <StatusLine
            message={banner.message}
            tone={banner.tone === "error" ? "error" : "success"}
          />
        )}
      </div>

      <div className={styles.body}>
        <ModelStackRail nodes={describedNodes} onAddNode={onAddNode} />
        <Canvas
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onAddNodeAt={placeNode}
          onRun={handleRun}
          running={running}
          runDisabled={!file}
        />
        <Inspector
          selectedNode={selectedNode}
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
