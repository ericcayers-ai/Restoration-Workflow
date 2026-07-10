"""Degradation analyzer v1 (ARCHITECTURE.md section 4).

Deliberately simple and heuristic, not learned — a fast, cheap classification
pass that runs before any heavy model loads:

- Blur estimate: variance of Laplacian.
- Noise estimate: high-frequency residual after a light (median) denoise pass.
- Face presence + count: a lightweight OpenCV detector when available
  (detection only, never restoration); ``None`` when unavailable.
- JPEG blockiness: 8x8 block-boundary gradient energy vs. interior energy.
- Exposure: histogram skew (low-light / blown-highlight detection).

Output is a structured DegradationProfile matched against a hand-authored
rule table (a plain data file, see rules.py) to pick Simple Mode's
auto-pipeline. Real and inspectable, not a stub that fakes intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .images import to_grayscale
from .types import ImageArray

_ANALYSIS_MAX_DIM = 1024  # analyze on a downscale; metrics that need native
                          # resolution (blockiness) run on the original.

# Blockiness is an unbounded ratio; clamp it so a near-flat interior can't send
# it to infinity and so the value stays comparable across images.
_MAX_BLOCKINESS = 8.0


@dataclass(frozen=True)
class DegradationProfile:
    width: int
    height: int
    blur_score: float          # Laplacian variance; LOWER = blurrier
    noise_score: float         # residual std estimate; higher = noisier
    jpeg_blockiness: float     # block-boundary energy ratio; ~0 = clean
    mean_luma: float           # 0-1
    dark_fraction: float       # fraction of pixels < 0.06
    bright_fraction: float     # fraction of pixels > 0.94
    face_count: int | None     # None = no detector available
    low_light: bool
    blown_highlights: bool

    @property
    def min_dimension(self) -> int:
        return min(self.width, self.height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "min_dimension": self.min_dimension,
            "blur_score": round(self.blur_score, 4),
            "noise_score": round(self.noise_score, 5),
            "jpeg_blockiness": round(self.jpeg_blockiness, 4),
            "mean_luma": round(self.mean_luma, 4),
            "dark_fraction": round(self.dark_fraction, 4),
            "bright_fraction": round(self.bright_fraction, 4),
            "face_count": self.face_count,
            "low_light": self.low_light,
            "blown_highlights": self.blown_highlights,
        }

    def metrics(self) -> dict[str, Any]:
        """Flat metric view the rule table conditions match against."""
        return self.to_dict()


def _downscale_gray(gray: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = gray.shape
    step = max(1, int(np.ceil(max(h, w) / max_dim)))
    return gray[::step, ::step]


def _laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float64)
    lap = (
        -4.0 * g[1:-1, 1:-1]
        + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    )
    # Scale to the conventional 0-255 Laplacian-variance range so thresholds
    # in the rule table match the values quoted in the literature.
    return float(np.var(lap * 255.0))


def _median3(gray: np.ndarray) -> np.ndarray:
    """3x3 median filter via shifted stacking (no scipy dependency)."""
    padded = np.pad(gray, 1, mode="edge")
    stack = np.stack([
        padded[dy:dy + gray.shape[0], dx:dx + gray.shape[1]]
        for dy in range(3) for dx in range(3)
    ])
    return np.median(stack, axis=0)


def _noise_estimate(gray: np.ndarray) -> float:
    residual = gray - _median3(gray)
    # Robust sigma from the median absolute deviation of the residual.
    return float(np.median(np.abs(residual)) / 0.6745)


def _jpeg_blockiness(gray: np.ndarray) -> float:
    h, w = gray.shape
    if h < 17 or w < 17:
        return 0.0
    col_diff = np.abs(np.diff(gray, axis=1))  # (h, w-1); diff i = cols i|i+1
    row_diff = np.abs(np.diff(gray, axis=0))
    # Gradients across 8x8 block boundaries vs. everywhere else.
    col_idx = np.arange(w - 1)
    row_idx = np.arange(h - 1)
    col_boundary = (col_idx % 8) == 7
    row_boundary = (row_idx % 8) == 7
    boundary = (
        float(col_diff[:, col_boundary].mean()) +
        float(row_diff[row_boundary, :].mean())
    ) / 2.0
    interior = (
        float(col_diff[:, ~col_boundary].mean()) +
        float(row_diff[~row_boundary, :].mean())
    ) / 2.0
    if interior <= 1e-8:
        # Flat block interiors with visible seams between them is the *most*
        # blocky an image can be, not the least: heavy quantization flattens
        # detail and leaves the seams. Returning 0.0 here — as a naive
        # divide-by-zero guard would — reports a maximally blocked image as
        # pristine and routes it away from FBCNN.
        return 0.0 if boundary <= 1e-8 else _MAX_BLOCKINESS
    return min(_MAX_BLOCKINESS, max(0.0, boundary / interior - 1.0))


def _detect_faces(gray_u8: np.ndarray) -> int | None:
    """Lightweight detection via OpenCV's bundled cascade; None if no cv2."""
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return None
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return None
    faces = cascade.detectMultiScale(gray_u8, scaleFactor=1.1, minNeighbors=5)
    return int(len(faces))


class DegradationAnalyzer:
    """analyze(image) -> DegradationProfile. Stateless and cheap."""

    def analyze(self, image: ImageArray) -> DegradationProfile:
        h, w = image.shape[:2]
        gray_full = to_grayscale(image)
        gray = _downscale_gray(gray_full, _ANALYSIS_MAX_DIM)

        mean_luma = float(gray.mean())
        dark_fraction = float((gray < 0.06).mean())
        bright_fraction = float((gray > 0.94).mean())

        gray_u8 = (np.clip(gray, 0, 1) * 255).astype(np.uint8)

        return DegradationProfile(
            width=w,
            height=h,
            blur_score=_laplacian_variance(gray),
            noise_score=_noise_estimate(gray),
            jpeg_blockiness=_jpeg_blockiness(gray_full),  # native res
            mean_luma=mean_luma,
            dark_fraction=dark_fraction,
            bright_fraction=bright_fraction,
            face_count=_detect_faces(gray_u8),
            low_light=mean_luma < 0.22 and dark_fraction > 0.30,
            blown_highlights=bright_fraction > 0.25,
        )
