/*
 * Computes the difference-heatmap view (UI_DESIGN.md section 7). Deliberately
 * colored within the app's own two-accent palette (surface -> amber) rather
 * than a generic rainbow/jet colormap — color stays inside the small,
 * meaning-bearing set the identity is built on (section 2), not borrowed from
 * a generic data-viz default.
 */

import { useEffect, useRef, useState } from "react";

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.trim().replace("#", "");
  const value = parseInt(clean.length === 3 ? clean.replace(/(.)/g, "$1$1") : clean, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`could not load ${url}`));
    img.src = url;
  });
}

export function useDifferenceImage(
  beforeUrl: string | null,
  afterUrl: string | null,
  enabled: boolean,
): { canvasRef: React.RefObject<HTMLCanvasElement>; ready: boolean; error: string | null } {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !beforeUrl || !afterUrl) return;
    let cancelled = false;
    setReady(false);
    setError(null);

    async function run() {
      try {
        const [before, after] = await Promise.all([loadImage(beforeUrl!), loadImage(afterUrl!)]);
        if (cancelled) return;

        const width = after.naturalWidth;
        const height = after.naturalHeight;

        const afterCanvas = document.createElement("canvas");
        afterCanvas.width = width;
        afterCanvas.height = height;
        const afterCtx = afterCanvas.getContext("2d");
        if (!afterCtx) throw new Error("2D canvas context unavailable");
        afterCtx.drawImage(after, 0, 0, width, height);
        const afterData = afterCtx.getImageData(0, 0, width, height);

        const beforeCanvas = document.createElement("canvas");
        beforeCanvas.width = width;
        beforeCanvas.height = height;
        const beforeCtx = beforeCanvas.getContext("2d");
        if (!beforeCtx) throw new Error("2D canvas context unavailable");
        // Scaled to the same box as `after` — the pipeline never crops, only
        // resamples, so a plain stretch keeps the same content aligned.
        beforeCtx.drawImage(before, 0, 0, width, height);
        const beforeData = beforeCtx.getImageData(0, 0, width, height);

        const style = getComputedStyle(document.documentElement);
        const cold = hexToRgb(style.getPropertyValue("--surface-950") || "#000000");
        const hot = hexToRgb(style.getPropertyValue("--accent-amber") || "#E8873A");

        const out = afterCtx.createImageData(width, height);
        const a = afterData.data;
        const b = beforeData.data;
        const o = out.data;
        for (let i = 0; i < a.length; i += 4) {
          const diff = (Math.abs(a[i]! - b[i]!) + Math.abs(a[i + 1]! - b[i + 1]!) + Math.abs(a[i + 2]! - b[i + 2]!)) / (3 * 255);
          o[i] = cold[0] + (hot[0] - cold[0]) * diff;
          o[i + 1] = cold[1] + (hot[1] - cold[1]) * diff;
          o[i + 2] = cold[2] + (hot[2] - cold[2]) * diff;
          o[i + 3] = 255;
        }

        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;
        canvas.width = width;
        canvas.height = height;
        canvas.getContext("2d")?.putImageData(out, 0, 0);
        setReady(true);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [beforeUrl, afterUrl, enabled]);

  return { canvasRef, ready, error };
}
