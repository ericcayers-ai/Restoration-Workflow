"""Soft-blend utilities for clip-mask highlight regeneration."""

from __future__ import annotations

import numpy as np

from .types import ImageArray


def soft_blend_masked(
    original: ImageArray,
    restored: ImageArray,
    mask: np.ndarray,
    *,
    feather: float = 0.15,
) -> ImageArray:
    """Blend ``restored`` into ``original`` only where ``mask`` is high.

    ``mask`` is HxW float in [0,1]. Optional ``feather`` expands the falloff
    by mixing with a box-blurred mask so edges aren't hard.
    """
    rgb_o = original[..., :3].astype(np.float32)
    rgb_r = restored[..., :3].astype(np.float32)
    if rgb_r.shape[:2] != rgb_o.shape[:2]:
        # Nearest-size resize via simple repeat/crop when shapes differ slightly.
        h, w = rgb_o.shape[:2]
        rgb_r = _resize_nearest(rgb_r, h, w)

    m = np.clip(mask.astype(np.float32), 0.0, 1.0)
    if m.ndim == 3:
        m = m[..., 0]
    if feather > 0:
        m = _box_blur(m, max(1, int(feather * min(m.shape) / 8)))
        m = np.clip(m, 0.0, 1.0)
    m3 = m[..., None]
    blended = rgb_o * (1.0 - m3) + rgb_r * m3

    if original.ndim == 3 and original.shape[2] == 4:
        return np.concatenate([blended, original[..., 3:4]], axis=2).astype(np.float32)
    return blended.astype(np.float32)


def _box_blur(gray: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return gray
    padded = np.pad(gray, radius, mode="edge")
    acc = np.zeros_like(gray, dtype=np.float64)
    span = 2 * radius + 1
    for dy in range(span):
        for dx in range(span):
            acc += padded[dy : dy + gray.shape[0], dx : dx + gray.shape[1]]
    return (acc / (span * span)).astype(np.float32)


def _resize_nearest(rgb: np.ndarray, h: int, w: int) -> np.ndarray:
    ys = (np.linspace(0, rgb.shape[0] - 1, h)).astype(np.int32)
    xs = (np.linspace(0, rgb.shape[1] - 1, w)).astype(np.int32)
    return rgb[ys][:, xs]
