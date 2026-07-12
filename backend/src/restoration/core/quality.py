"""Quality tiers: draft / balanced / high (ROADMAP.md Phase 4.5.4).

A user-facing "how long are you willing to wait" axis, layered on top of —
not a replacement for — the hardware VRAM-tier gating in hardware.py and the
executor's own OOM-retry-with-tiling fallback (ARCHITECTURE.md section 4).
Draft trades quality for speed and OOM headroom; high trades speed for
quality, still bounded by what the detected hardware can actually run without
OOMing. Balanced is the rule table's own decision, unchanged.

This only ever changes *which* model fills a role the rule table already
decided the image needs, and how big a tile that model runs at — it never
adds a stage the image didn't already call for (draft doesn't skip a face
pass a photo doesn't have a face in, high doesn't invent one either).
"""

from __future__ import annotations

import enum
from typing import Any

from .hardware import HardwareInfo
from .registry import NodeRegistry


class QualityTier(str, enum.Enum):
    DRAFT = "draft"
    BALANCED = "balanced"
    HIGH = "high"


# Tile size per (minimum detected VRAM, tier), smallest-safe band first. 0
# disables tiling (whole-image inference) once there's plainly enough
# headroom that seams from tiling would be a needless quality cost.
_TILE_BANDS: list[tuple[int, dict[QualityTier, int]]] = [
    (0, {QualityTier.DRAFT: 192, QualityTier.BALANCED: 320, QualityTier.HIGH: 384}),
    (8 * 1024, {QualityTier.DRAFT: 320, QualityTier.BALANCED: 512, QualityTier.HIGH: 640}),
    (16 * 1024, {QualityTier.DRAFT: 512, QualityTier.BALANCED: 768, QualityTier.HIGH: 0}),
]

# The one substitutable pair per role today; a role with only one in-box
# model (e.g. denoise -> scunet) has nothing to swap and is left alone.
_UPSCALE_FAST = "realesrgan"
_UPSCALE_QUALITY = "swinir"
_FACE_FAST = "gfpgan"
_FACE_QUALITY = "restoreformer"


def tile_size_for(tier: QualityTier, hardware: HardwareInfo) -> int:
    """A tile size biased smaller (safer, faster feedback) in draft and
    larger (fewer seams) in high, bounded by the smallest tested VRAM band so
    no tier ever OOMs there. CPU-only gets the most conservative band —
    there's no VRAM ceiling to reason about, but wall-clock time still is."""
    vram = hardware.max_vram_mb if hardware.backend != "cpu" else 0
    chosen = _TILE_BANDS[0][1]
    for min_vram, sizes in _TILE_BANDS:
        if vram >= min_vram:
            chosen = sizes
    return chosen[tier]


def apply_quality_tier(
    chain: list[str],
    params: dict[str, dict[str, Any]],
    tier: QualityTier,
    hardware: HardwareInfo,
    registry: NodeRegistry,
    *,
    quality_upscale_ready: bool = True,
    quality_face_ready: bool = True,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Adjust an already-routed chain's model choice and tile sizes for a
    quality tier. ``quality_upscale_ready`` / ``quality_face_ready`` should
    reflect whether that role's "quality" model is already installed — a
    tier preference is never itself a trigger for a multi-hundred-megabyte
    automatic download, so callers pass ``False`` when it isn't and High tier
    simply keeps the fast model for that role instead."""
    chain = list(chain)
    params = {k: dict(v) for k, v in params.items()}

    def swap(old: str, new: str) -> None:
        if old in chain and new not in chain:
            chain[chain.index(old)] = new
            if old in params:
                params[new] = params.pop(old)

    if tier is QualityTier.DRAFT:
        swap(_UPSCALE_QUALITY, _UPSCALE_FAST)
        # A follow-up quality face pass is a second full model load for a
        # difference draft mode is explicitly trading away for speed.
        if _FACE_QUALITY in chain and _FACE_FAST in chain:
            chain.remove(_FACE_QUALITY)
            params.pop(_FACE_QUALITY, None)
    elif tier is QualityTier.HIGH:
        if quality_upscale_ready:
            swap(_UPSCALE_FAST, _UPSCALE_QUALITY)
        if quality_face_ready and _FACE_FAST in chain and _FACE_QUALITY not in chain:
            chain.insert(chain.index(_FACE_FAST) + 1, _FACE_QUALITY)
    # BALANCED: the rule table's own chain, unchanged.

    tile = tile_size_for(tier, hardware)
    for node_type in chain:
        node_cls = registry.get_class(node_type)
        if node_cls.supports_tiling:
            node_params = params.setdefault(node_type, {})
            node_params["tile"] = tile
            node_params.setdefault("tile_pad", 32)

    return chain, params
