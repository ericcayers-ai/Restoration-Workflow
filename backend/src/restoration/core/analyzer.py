"""Degradation analyzer v2 (ARCHITECTURE.md section 4).

Deliberately heuristic, not learned — a fast classification pass that runs
before any heavy model loads. v2 adds multi-scale blur, anisotropy, better
noise-vs-texture separation, continuous exposure / clip-mask signals, chroma
/ grayscale detection, and per-metric confidence so Auto and ensembles can
explain *why* a stage was chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .images import to_grayscale
from .types import ImageArray

_ANALYSIS_MAX_DIM = 1024
_MAX_BLOCKINESS = 8.0

# Face detector thresholds — tighten Haar false positives on texture/noise.
_FACE_SCALE = 1.15
_FACE_MIN_NEIGHBORS = 7
_FACE_MIN_SIZE_FRAC = 0.08  # reject detections smaller than 8% of min dim


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
    defect_score: float = 0.0
    # --- v2 fields ----------------------------------------------------------
    blur_anisotropy: float = 0.0       # |h_grad - v_grad| / (h+v); motion-blur hint
    under_exposure: float = 0.0        # continuous 0-1 underexposure severity
    over_exposure: float = 0.0         # continuous 0-1 overexposure severity
    clip_fraction: float = 0.0         # fraction of near-clipped highlight pixels
    mean_saturation: float = 0.0       # mean chroma (HSV S)
    is_grayscale: bool = False
    chroma_blockiness: float = 0.0     # optional chroma-plane JPEG hint
    confidence: dict[str, float] = field(default_factory=dict)

    @property
    def min_dimension(self) -> int:
        return min(self.width, self.height)

    @staticmethod
    def clip_mask(image: ImageArray, threshold: float = 0.97) -> np.ndarray:
        """Soft float mask (H,W) in [0,1] for near-clipped highlights."""
        rgb = image[..., :3] if image.ndim == 3 and image.shape[-1] >= 3 else image
        if rgb.ndim == 2:
            luma = rgb.astype(np.float32)
        else:
            luma = (
                0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
            ).astype(np.float32)
        # Soft ramp from threshold→1.0 so blend edges aren't hard.
        soft = np.clip((luma - threshold) / max(1e-6, 1.0 - threshold), 0.0, 1.0)
        return soft.astype(np.float32)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DegradationProfile:
        """Rebuild a profile from ``to_dict()`` (ensemble API profile passthrough)."""
        return cls(
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            blur_score=float(data.get("blur_score", 0.0)),
            noise_score=float(data.get("noise_score", 0.0)),
            jpeg_blockiness=float(data.get("jpeg_blockiness", 0.0)),
            mean_luma=float(data.get("mean_luma", 0.5)),
            dark_fraction=float(data.get("dark_fraction", 0.0)),
            bright_fraction=float(data.get("bright_fraction", 0.0)),
            face_count=data.get("face_count"),
            low_light=bool(data.get("low_light", False)),
            blown_highlights=bool(data.get("blown_highlights", False)),
            defect_score=float(data.get("defect_score", 0.0)),
            blur_anisotropy=float(data.get("blur_anisotropy", 0.0)),
            under_exposure=float(data.get("under_exposure", 0.0)),
            over_exposure=float(data.get("over_exposure", 0.0)),
            clip_fraction=float(data.get("clip_fraction", 0.0)),
            mean_saturation=float(data.get("mean_saturation", 0.0)),
            is_grayscale=bool(data.get("is_grayscale", False)),
            chroma_blockiness=float(data.get("chroma_blockiness", 0.0)),
            confidence=dict(data.get("confidence") or {}),
        )

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
            "defect_score": round(self.defect_score, 5),
            "blur_anisotropy": round(self.blur_anisotropy, 4),
            "under_exposure": round(self.under_exposure, 4),
            "over_exposure": round(self.over_exposure, 4),
            "clip_fraction": round(self.clip_fraction, 5),
            "mean_saturation": round(self.mean_saturation, 4),
            "is_grayscale": self.is_grayscale,
            "chroma_blockiness": round(self.chroma_blockiness, 4),
            "confidence": {k: round(v, 3) for k, v in self.confidence.items()},
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
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = (
        -4.0 * g[1:-1, 1:-1]
        + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    )
    return float(np.var(lap * 255.0))


def _sobel_energy(gray: np.ndarray) -> tuple[float, float]:
    """Horizontal and vertical gradient energies for anisotropy."""
    g = gray.astype(np.float64)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0, 0.0
    gx = g[:, 2:] - g[:, :-2]
    gy = g[2:, :] - g[:-2, :]
    # Align shapes to overlapping interior (crop to shared sobel regions).
    gx_c = gx[1:-1, :] if gx.shape[0] > 2 else gx
    gy_c = gy[:, 1:-1] if gy.shape[1] > 2 else gy
    hh = min(gx_c.shape[0], gy_c.shape[0])
    ww = min(gx_c.shape[1], gy_c.shape[1])
    if hh < 1 or ww < 1:
        return float(np.mean(np.abs(gx))), float(np.mean(np.abs(gy)))
    return float(np.mean(np.abs(gx_c[:hh, :ww]))), float(np.mean(np.abs(gy_c[:hh, :ww])))


def _blur_anisotropy(gray: np.ndarray) -> float:
    hx, vy = _sobel_energy(gray)
    denom = hx + vy
    if denom < 1e-8:
        return 0.0
    return float(abs(hx - vy) / denom)


def _multi_scale_blur(gray: np.ndarray) -> float:
    """Blend full-res and half-res Laplacian variances (geometric mean)."""
    full = _laplacian_variance(gray)
    half = gray[::2, ::2]
    half_score = _laplacian_variance(half) if half.size > 16 else full
    if full <= 0 or half_score <= 0:
        return float(full)
    return float(np.sqrt(full * half_score))


def _median_filter(gray: np.ndarray, size: int) -> np.ndarray:
    """``size``x``size`` median filter via shifted stacking (no scipy dependency)."""
    radius = size // 2
    padded = np.pad(gray, radius, mode="edge")
    stack = np.stack([
        padded[dy:dy + gray.shape[0], dx:dx + gray.shape[1]]
        for dy in range(size) for dx in range(size)
    ])
    return np.median(stack, axis=0)


def _median3(gray: np.ndarray) -> np.ndarray:
    return _median_filter(gray, 3)


def _noise_estimate(gray: np.ndarray) -> float:
    """Robust residual sigma, attenuated in high-edge (texture) regions."""
    residual = gray - _median3(gray)
    abs_res = np.abs(residual)
    # Edge map: suppress residuals on strong gradients so texture isn't noise.
    hx, vy = _sobel_energy(gray)
    # Per-pixel rough edge strength via local gradient approx.
    g = gray.astype(np.float64)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return float(np.median(abs_res) / 0.6745)
    gx = np.abs(np.diff(g, axis=1))
    gy = np.abs(np.diff(g, axis=0))
    edge = np.zeros_like(g)
    edge[:, 1:] += gx
    edge[1:, :] += gy
    edge_thresh = max(float(np.percentile(edge, 75)), 1e-4)
    flat = edge < edge_thresh
    if flat.mean() < 0.05:
        return float(np.median(abs_res) / 0.6745)
    return float(np.median(abs_res[flat]) / 0.6745)


_DEFECT_MEDIAN_WINDOW = 5
_DEFECT_RESIDUAL_THRESHOLD = 0.15
_DEFECT_EXTREME_LOW = 0.12
_DEFECT_EXTREME_HIGH = 0.88


def _defect_score(gray: np.ndarray) -> float:
    residual = np.abs(gray - _median_filter(gray, _DEFECT_MEDIAN_WINDOW))
    extreme = (gray < _DEFECT_EXTREME_LOW) | (gray > _DEFECT_EXTREME_HIGH)
    candidate = extreme & (residual > _DEFECT_RESIDUAL_THRESHOLD)
    return float(candidate.mean())


def _jpeg_blockiness(gray: np.ndarray) -> float:
    h, w = gray.shape
    if h < 17 or w < 17:
        return 0.0
    col_diff = np.abs(np.diff(gray, axis=1))
    row_diff = np.abs(np.diff(gray, axis=0))
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
        return 0.0 if boundary <= 1e-8 else _MAX_BLOCKINESS
    return min(_MAX_BLOCKINESS, max(0.0, boundary / interior - 1.0))


def _chroma_blockiness(image: ImageArray) -> float:
    """JPEG chroma-subsampling hint from the Cb/Cr-ish planes."""
    if image.ndim != 3 or image.shape[2] < 3:
        return 0.0
    rgb = image[..., :3].astype(np.float64)
    # Approximate Cr / Cb without full YCbCr: R-Y and B-Y residuals.
    y = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    cr = rgb[..., 0] - y
    cb = rgb[..., 2] - y
    # Analyze at half res — chroma was often subsampled 2:1.
    cr_ds = cr[::2, ::2]
    cb_ds = cb[::2, ::2]
    return max(_jpeg_blockiness(cr_ds), _jpeg_blockiness(cb_ds)) * 0.5


def _saturation_stats(image: ImageArray) -> tuple[float, bool]:
    if image.ndim != 3 or image.shape[2] < 3:
        return 0.0, True
    rgb = np.clip(image[..., :3], 0, 1).astype(np.float64)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    # Avoid div-by-zero on pure black.
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 1e-6)
    mean_sat = float(sat.mean())
    # Near-zero channel variance → grayscale (allow tiny noise).
    channel_std = float(np.std(rgb, axis=2).mean())
    is_gray = mean_sat < 0.035 and channel_std < 0.02
    return mean_sat, is_gray


def _exposure_scores(
    gray: np.ndarray, mean_luma: float, dark_fraction: float, bright_fraction: float
) -> tuple[float, float, float, bool, bool]:
    """Continuous under/over scores, clip fraction, and boolean flags."""
    clip_fraction = float((gray >= 0.97).mean())
    under = float(np.clip((0.35 - mean_luma) / 0.35 + dark_fraction * 0.5, 0.0, 1.0))
    over = float(np.clip((mean_luma - 0.65) / 0.35 + bright_fraction * 0.5, 0.0, 1.0))
    # Soften when midtones dominate.
    if 0.25 < mean_luma < 0.75 and dark_fraction < 0.15 and bright_fraction < 0.15:
        under *= 0.3
        over *= 0.3
    low_light = mean_luma < 0.22 and dark_fraction > 0.30
    blown = bright_fraction > 0.18 or clip_fraction > 0.04
    return under, over, clip_fraction, low_light, blown


def _detect_faces(gray_u8: np.ndarray) -> int | None:
    """Lightweight detection via OpenCV cascade; tighter minNeighbors / size."""
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return None
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return None
    h, w = gray_u8.shape[:2]
    min_side = max(24, int(min(h, w) * _FACE_MIN_SIZE_FRAC))
    faces = cascade.detectMultiScale(
        gray_u8,
        scaleFactor=_FACE_SCALE,
        minNeighbors=_FACE_MIN_NEIGHBORS,
        minSize=(min_side, min_side),
    )
    return int(len(faces))


def _confidences(
    *,
    blur_score: float,
    noise_score: float,
    jpeg_blockiness: float,
    under: float,
    over: float,
    face_count: int | None,
    is_grayscale: bool,
    defect_score: float,
) -> dict[str, float]:
    """Rough 0-1 confidence that the metric is meaningful (not borderline)."""

    def band(score: float, lo: float, hi: float) -> float:
        if score <= lo or score >= hi:
            return 0.95
        mid = (lo + hi) / 2
        span = (hi - lo) / 2 or 1.0
        return float(np.clip(abs(score - mid) / span, 0.2, 0.95))

    return {
        "blur": band(blur_score, 40.0, 200.0),
        "noise": band(noise_score, 0.004, 0.02),
        "jpeg": band(jpeg_blockiness, 0.05, 0.25),
        "exposure": max(under, over, 0.25),
        "faces": 0.85 if face_count and face_count > 0 else (0.5 if face_count == 0 else 0.0),
        "grayscale": 0.9 if is_grayscale else 0.7,
        "defects": band(defect_score, 0.005, 0.03),
    }


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
        noise_score = _noise_estimate(gray)
        blur_score = _multi_scale_blur(gray)
        anisotropy = _blur_anisotropy(gray)
        under, over, clip_frac, low_light, blown = _exposure_scores(
            gray, mean_luma, dark_fraction, bright_fraction
        )
        mean_sat, is_gray = _saturation_stats(image)
        face_count = _detect_faces(gray_u8)
        defect = _defect_score(gray)
        jpeg = _jpeg_blockiness(gray_full)
        chroma = _chroma_blockiness(image)

        conf = _confidences(
            blur_score=blur_score,
            noise_score=noise_score,
            jpeg_blockiness=jpeg,
            under=under,
            over=over,
            face_count=face_count,
            is_grayscale=is_gray,
            defect_score=defect,
        )

        return DegradationProfile(
            width=w,
            height=h,
            blur_score=blur_score,
            noise_score=noise_score,
            jpeg_blockiness=jpeg,
            mean_luma=mean_luma,
            dark_fraction=dark_fraction,
            bright_fraction=bright_fraction,
            face_count=face_count,
            low_light=low_light,
            blown_highlights=blown,
            defect_score=defect,
            blur_anisotropy=anisotropy,
            under_exposure=under,
            over_exposure=over,
            clip_fraction=clip_frac,
            mean_saturation=mean_sat,
            is_grayscale=is_gray,
            chroma_blockiness=chroma,
            confidence=conf,
        )
