/*
 * "Result appears on a light-table: the restored image sits on a neutral
 * warm-gray mat with a draggable vertical divider revealing before/after.
 * A secondary toggle offers side-by-side and (for the curious) a
 * difference-heatmap view." (UI_DESIGN.md section 7)
 */

import { useState } from "react";
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
}: {
  beforeUrl: string;
  afterUrl: string;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}) {
  const t = useT();
  const [position, setPosition] = useState(50);
  const [aspectRatio, setAspectRatio] = useState<string>("4 / 3");
  const diff = useDifferenceImage(beforeUrl, afterUrl, viewMode === "difference");

  return (
    <div className={`${styles.mat} grain-surface`}>
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
      </div>

      {/* The slider view's two layers are both position:absolute (so they can
          overlap), which means neither contributes to normal-flow height —
          without an explicit aspect-ratio here, .frame collapses to 0px tall
          and the whole comparison silently disappears. Side-by-side and the
          difference canvas happen to survive without this (an <img>/<canvas>
          is a replaced element that falls back to its own intrinsic aspect
          ratio), but deriving it once, from the real "after" image, is the
          same fix applied uniformly rather than relying on that accident. */}
      <div className={styles.frame} style={{ aspectRatio }}>
        {viewMode === "slider" && (
          <div className={styles.compareArea}>
            <img
              className={styles.layerBase}
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
  );
}
