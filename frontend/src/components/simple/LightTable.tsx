/*
 * "Result appears on a light-table: the restored image sits on a neutral
 * warm-gray mat with a draggable vertical divider revealing before/after.
 * A secondary toggle offers side-by-side and (for the curious) a
 * difference-heatmap view." (UI_DESIGN.md section 7)
 */

import { useEffect, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { useDifferenceImage } from "../../lib/useDifferenceImage";
import styles from "./LightTable.module.css";

type ViewMode = "slider" | "side-by-side" | "difference";

const MODES: { value: ViewMode; key: "simple.viewMode.slider" | "simple.viewMode.sideBySide" | "simple.viewMode.difference" }[] = [
  { value: "slider", key: "simple.viewMode.slider" },
  { value: "side-by-side", key: "simple.viewMode.sideBySide" },
  { value: "difference", key: "simple.viewMode.difference" },
];

export function LightTable({
  beforeUrl,
  afterUrl,
  viewMode,
  onViewModeChange,
  reveal = false,
}: {
  beforeUrl: string;
  afterUrl: string;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  /** Fade the restored result in once complete (ROADMAP.md 4.5.7). */
  reveal?: boolean;
}) {
  const t = useT();
  const [position, setPosition] = useState(50);
  const [aspectRatio, setAspectRatio] = useState<string>("4 / 3");
  const [fadeIn, setFadeIn] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panStart = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const diff = useDifferenceImage(beforeUrl, afterUrl, viewMode === "difference");

  useEffect(() => {
    if (!reveal) return;
    setFadeIn(false);
    const timer = window.setTimeout(() => setFadeIn(true), 80);
    return () => window.clearTimeout(timer);
  }, [afterUrl, reveal]);

  function onWheel(e: React.WheelEvent) {
    e.preventDefault();
    setZoom((z) => Math.min(4, Math.max(1, z + (e.deltaY < 0 ? 0.1 : -0.1))));
  }

  return (
    <div className={styles.mat}>
      <div className={styles.viewModeRow}>
        <div className={styles.segmented} role="radiogroup" aria-label="Comparison view">
          {MODES.map((mode) => (
            <button
              key={mode.value}
              type="button"
              role="radio"
              aria-checked={viewMode === mode.value}
              className={`${styles.segment} ${viewMode === mode.value ? styles.segmentActive : ""}`}
              onClick={() => onViewModeChange(mode.value)}
            >
              {t(mode.key)}
            </button>
          ))}
        </div>
        <div className={styles.zoomControls}>
          <button type="button" className={styles.zoomBtn} onClick={() => setZoom((z) => Math.max(1, z - 0.25))}>−</button>
          <span className="mono">{Math.round(zoom * 100)}%</span>
          <button type="button" className={styles.zoomBtn} onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>+</button>
          <button type="button" className={styles.zoomBtn} onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>{t("simple.zoom.reset")}</button>
        </div>
      </div>

      <div
        className={styles.frame}
        style={{ aspectRatio }}
        onWheel={onWheel}
        onPointerDown={(e) => {
          if (zoom <= 1) return;
          panStart.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!panStart.current) return;
          setPan({
            x: panStart.current.px + (e.clientX - panStart.current.x),
            y: panStart.current.py + (e.clientY - panStart.current.y),
          });
        }}
        onPointerUp={() => { panStart.current = null; }}
      >
        <div
          className={styles.zoomLayer}
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
        {viewMode === "slider" && (
          <div className={styles.compareArea}>
            <img
              className={`${styles.layerBase} ${reveal && fadeIn ? styles.revealed : ""}`}
              src={afterUrl}
              alt={t("simple.after")}
              onLoad={(e) => {
                const img = e.currentTarget;
                setAspectRatio(`${img.naturalWidth} / ${img.naturalHeight}`);
              }}
            />
            <div className={styles.beforeClip} style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}>
              <img className={styles.layerBase} src={beforeUrl} alt={t("simple.before")} />
            </div>
            <div className={styles.dividerLine} style={{ left: `${position}%` }} />
            <input
              className={styles.rangeInput}
              type="range"
              min={0}
              max={100}
              value={position}
              onChange={(e) => setPosition(Number(e.target.value))}
              aria-label={`${t("simple.before")} / ${t("simple.after")}`}
              aria-valuetext={`${position}%`}
            />
          </div>
        )}

        {viewMode === "side-by-side" && (
          <div className={styles.sideBySide}>
            <figure>
              <img src={beforeUrl} alt={t("simple.before")} />
              <figcaption className={styles.caption}>{t("simple.before")}</figcaption>
            </figure>
            <figure>
              <img src={afterUrl} alt={t("simple.after")} />
              <figcaption className={styles.caption}>{t("simple.after")}</figcaption>
            </figure>
          </div>
        )}

        {viewMode === "difference" && (
          <>
            {diff.error && <p className={styles.diffStatus}>{diff.error}</p>}
            {!diff.ready && !diff.error && <p className={styles.diffStatus}>{t("common.loading")}</p>}
            <canvas
              ref={diff.canvasRef}
              className={styles.diffCanvas}
              style={{ display: diff.ready ? "block" : "none" }}
            />
          </>
        )}
        </div>
      </div>
    </div>
  );
}
