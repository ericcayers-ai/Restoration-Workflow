/*
 * Mask Editor — third app mode for painting inpaint regions and running
 * scratch / segment / inpaint tools against the painted mask (plan Phase 3).
 * Safelight product register: restrained chrome, existing tokens, no SaaS cards.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  detectScratchMask,
  inpaintWithMask,
  segmentMask,
  uploadMask,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PipelineJson } from "../../lib/types";
import { Button } from "../common/Button";
import { StatusLine } from "../common/StatusLine";
import { DropZone } from "../simple/DropZone";
import styles from "./MaskEditor.module.css";

export type MaskExportTarget = "studio" | "simple";

export interface MaskExportPayload {
  file: File;
  maskId: string;
  pipeline: PipelineJson;
  target: MaskExportTarget;
}

type Tool = "brush" | "erase";

function buildInpaintPipeline(maskId: string): PipelineJson {
  return {
    version: 1,
    nodes: [
      {
        id: "mask_1",
        type: "load_mask",
        params: { source: "asset", mask_id: maskId, invert: false },
        pinned: false,
      },
      {
        id: "lama_1",
        type: "lama",
        params: { mask_threshold: 0.5 },
        pinned: false,
      },
    ],
    edges: [{ from: "mask_1", to: "lama_1", to_input: "mask" }],
  };
}

async function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Failed to encode mask"));
    }, "image/png");
  });
}

function loadImageBitmap(file: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Failed to load image"));
    };
    img.src = url;
  });
}

export function MaskEditor({
  onExport,
}: {
  onExport: (payload: MaskExportPayload) => void;
}) {
  const t = useT();
  const [file, setFile] = useState<File | null>(null);
  const [tool, setTool] = useState<Tool>("brush");
  const [brushSize, setBrushSize] = useState(28);
  const [feather, setFeather] = useState(2);
  const [busy, setBusy] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ message: string; tone: "error" | "success" } | null>(
    null,
  );
  const [resultUrl, setResultUrl] = useState<string | null>(null);

  const photoRef = useRef<HTMLCanvasElement>(null);
  const maskRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const naturalSize = useRef<{ w: number; h: number }>({ w: 0, h: 0 });

  const paintOverlay = useCallback(() => {
    const mask = maskRef.current;
    const overlay = overlayRef.current;
    if (!mask || !overlay) return;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.drawImage(mask, 0, 0);
    ctx.globalCompositeOperation = "source-in";
    ctx.fillStyle = "rgba(193, 149, 63, 0.45)";
    ctx.fillRect(0, 0, overlay.width, overlay.height);
    ctx.globalCompositeOperation = "source-over";
  }, []);

  const initCanvases = useCallback(
    async (next: File) => {
      const img = await loadImageBitmap(next);
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      naturalSize.current = { w, h };
      for (const ref of [photoRef, maskRef, overlayRef]) {
        const canvas = ref.current;
        if (!canvas) continue;
        canvas.width = w;
        canvas.height = h;
      }
      const photoCtx = photoRef.current?.getContext("2d");
      photoCtx?.drawImage(img, 0, 0);
      const maskCtx = maskRef.current?.getContext("2d");
      if (maskCtx) {
        maskCtx.clearRect(0, 0, w, h);
        maskCtx.fillStyle = "#000";
        maskCtx.fillRect(0, 0, w, h);
      }
      paintOverlay();
      setResultUrl(null);
      setBanner(null);
    },
    [paintOverlay],
  );

  useEffect(() => {
    if (file) void initCanvases(file);
  }, [file, initCanvases]);

  useEffect(() => {
    if (!file) return;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      const key = e.key.toLowerCase();
      if (key === "b") {
        setTool("brush");
      } else if (key === "e") {
        setTool("erase");
      } else if (key === "i" && !e.metaKey && !e.ctrlKey) {
        invertMask();
      } else if (key === "escape") {
        clearMask();
      } else if (e.key === "[") {
        setBrushSize((s) => Math.max(4, s - 4));
      } else if (e.key === "]") {
        setBrushSize((s) => Math.min(120, s + 4));
      } else {
        return;
      }
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [file]);

  function canvasPoint(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = overlayRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((e.clientY - rect.top) / rect.height) * canvas.height;
    return { x, y };
  }

  function stroke(from: { x: number; y: number }, to: { x: number; y: number }) {
    const mask = maskRef.current;
    const ctx = mask?.getContext("2d");
    if (!ctx || !mask) return;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = brushSize;
    ctx.shadowBlur = feather;
    ctx.shadowColor = tool === "brush" ? "#fff" : "#000";
    ctx.strokeStyle = tool === "brush" ? "#fff" : "#000";
    ctx.globalCompositeOperation = "source-over";
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    paintOverlay();
  }

  function invertMask() {
    const mask = maskRef.current;
    const ctx = mask?.getContext("2d");
    if (!ctx || !mask) return;
    const image = ctx.getImageData(0, 0, mask.width, mask.height);
    const data = image.data;
    for (let i = 0; i < data.length; i += 4) {
      data[i] = 255 - (data[i] ?? 0);
      data[i + 1] = 255 - (data[i + 1] ?? 0);
      data[i + 2] = 255 - (data[i + 2] ?? 0);
    }
    ctx.putImageData(image, 0, 0);
    paintOverlay();
  }

  function clearMask() {
    const mask = maskRef.current;
    const ctx = mask?.getContext("2d");
    if (!ctx || !mask) return;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, mask.width, mask.height);
    paintOverlay();
  }

  async function applyMaskBlob(blob: Blob) {
    const img = await loadImageBitmap(blob);
    const mask = maskRef.current;
    const ctx = mask?.getContext("2d");
    if (!ctx || !mask) return;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, mask.width, mask.height);
    ctx.drawImage(img, 0, 0, mask.width, mask.height);
    paintOverlay();
  }

  async function runScratch() {
    if (!file) return;
    setBusy(t("mask.busy.scratch"));
    setBanner(null);
    try {
      const blob = await detectScratchMask(file);
      await applyMaskBlob(blob);
      setBanner({ message: t("mask.banner.scratch"), tone: "success" });
    } catch (err) {
      setBanner({ message: err instanceof Error ? err.message : String(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function runSegment() {
    if (!file) return;
    setBusy(t("mask.busy.segment"));
    setBanner(null);
    try {
      const { url } = await segmentMask(file);
      const resp = await fetch(url);
      await applyMaskBlob(await resp.blob());
      setBanner({ message: t("mask.banner.segment"), tone: "success" });
    } catch (err) {
      setBanner({ message: err instanceof Error ? err.message : String(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function runInpaint(engine: "lama" | "powerpaint" | "flux_fill") {
    if (!file || !maskRef.current) return;
    setBusy(t("mask.busy.inpaint"));
    setBanner(null);
    try {
      const maskBlob = await canvasToPngBlob(maskRef.current);
      const result = await inpaintWithMask(file, maskBlob, engine);
      if (resultUrl) URL.revokeObjectURL(resultUrl);
      setResultUrl(URL.createObjectURL(result));
      setBanner({ message: t("mask.banner.inpaint"), tone: "success" });
    } catch (err) {
      setBanner({ message: err instanceof Error ? err.message : String(err), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function exportMask(target: MaskExportTarget) {
    if (!file || !maskRef.current) return;
    setBusy(t("mask.busy.export"));
    setBanner(null);
    try {
      const maskBlob = await canvasToPngBlob(maskRef.current);
      const { id } = await uploadMask(maskBlob);
      onExport({
        file,
        maskId: id,
        pipeline: buildInpaintPipeline(id),
        target,
      });
    } catch (err) {
      setBanner({ message: err instanceof Error ? err.message : String(err), tone: "error" });
      setBusy(null);
    }
  }

  if (!file) {
    return (
      <div className={styles.root}>
        <header className={styles.intro}>
          <h1 className={styles.title}>{t("mask.title")}</h1>
          <p className={styles.lede}>{t("mask.lede")}</p>
        </header>
        <DropZone onFile={setFile} />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <div className={styles.toolbar} role="toolbar" aria-label={t("mask.toolbar")}>
        <div className={styles.toolGroup} role="group" aria-label={t("mask.toolbar")}>
          <button
            type="button"
            className={tool === "brush" ? styles.toolActive : styles.tool}
            aria-pressed={tool === "brush"}
            aria-keyshortcuts="B"
            onClick={() => setTool("brush")}
          >
            {t("mask.tool.brush")}
          </button>
          <button
            type="button"
            className={tool === "erase" ? styles.toolActive : styles.tool}
            aria-pressed={tool === "erase"}
            aria-keyshortcuts="E"
            onClick={() => setTool("erase")}
          >
            {t("mask.tool.erase")}
          </button>
          <button
            type="button"
            className={styles.tool}
            aria-keyshortcuts="I"
            onClick={invertMask}
          >
            {t("mask.tool.invert")}
          </button>
          <button
            type="button"
            className={styles.tool}
            aria-keyshortcuts="Escape"
            onClick={clearMask}
          >
            {t("mask.tool.clear")}
          </button>
        </div>
        <label className={styles.slider}>
          <span>{t("mask.brushSize")}</span>
          <input
            type="range"
            min={4}
            max={120}
            value={brushSize}
            aria-valuetext={t("mask.brushSizeValue", { value: String(brushSize) })}
            onChange={(e) => setBrushSize(Number(e.target.value))}
          />
          <span className={styles.sliderValue} aria-hidden>
            {brushSize}
          </span>
        </label>
        <label className={styles.slider}>
          <span>{t("mask.feather")}</span>
          <input
            type="range"
            min={0}
            max={24}
            value={feather}
            aria-valuetext={t("mask.featherValue", { value: String(feather) })}
            onChange={(e) => setFeather(Number(e.target.value))}
          />
          <span className={styles.sliderValue} aria-hidden>
            {feather}
          </span>
        </label>
        <div className={styles.spacer} />
        <Button variant="ghost" size="small" onClick={() => setFile(null)}>
          {t("mask.newPhoto")}
        </Button>
      </div>
      <p className={styles.shortcuts}>{t("mask.shortcuts")}</p>

      <div className={styles.workspace}>
        <div className={styles.stage}>
          <canvas ref={photoRef} className={styles.photo} aria-hidden />
          <canvas
            ref={overlayRef}
            className={styles.overlay}
            tabIndex={0}
            role="img"
            aria-label={t("mask.canvasLabel")}
            onPointerDown={(e) => {
              const pt = canvasPoint(e);
              if (!pt) return;
              drawing.current = true;
              last.current = pt;
              stroke(pt, pt);
              (e.target as HTMLElement).setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              if (!drawing.current || !last.current) return;
              const pt = canvasPoint(e);
              if (!pt) return;
              stroke(last.current, pt);
              last.current = pt;
            }}
            onPointerUp={() => {
              drawing.current = false;
              last.current = null;
            }}
          />
          <canvas ref={maskRef} className={styles.hiddenMask} aria-hidden />
        </div>

        <aside className={styles.side} aria-label={t("mask.sideTools")}>
          <h2>{t("mask.autoTools")}</h2>
          <Button variant="secondary" disabled={!!busy} onClick={() => void runScratch()}>
            {t("mask.auto.scratch")}
          </Button>
          <Button variant="secondary" disabled={!!busy} onClick={() => void runSegment()}>
            {t("mask.auto.segment")}
          </Button>
          <h2>{t("mask.inpaintTools")}</h2>
          <Button variant="secondary" disabled={!!busy} onClick={() => void runInpaint("lama")}>
            {t("mask.inpaint.lama")}
          </Button>
          <Button
            variant="secondary"
            disabled={!!busy}
            onClick={() => void runInpaint("powerpaint")}
          >
            {t("mask.inpaint.powerpaint")}
          </Button>
          <Button
            variant="secondary"
            disabled={!!busy}
            onClick={() => void runInpaint("flux_fill")}
          >
            {t("mask.inpaint.flux")}
          </Button>
          <h2>{t("mask.export")}</h2>
          <Button variant="primary" disabled={!!busy} onClick={() => void exportMask("studio")}>
            {t("mask.export.studio")}
          </Button>
          <Button variant="secondary" disabled={!!busy} onClick={() => void exportMask("simple")}>
            {t("mask.export.simple")}
          </Button>
          {resultUrl && (
            <div className={styles.preview}>
              <p>{t("mask.inpaintResult")}</p>
              <img src={resultUrl} alt={t("mask.inpaintResult")} />
            </div>
          )}
        </aside>
      </div>

      {busy && <StatusLine message={busy} />}
      {banner && (
        <StatusLine message={banner.message} tone={banner.tone === "error" ? "error" : "success"} />
      )}
    </div>
  );
}
