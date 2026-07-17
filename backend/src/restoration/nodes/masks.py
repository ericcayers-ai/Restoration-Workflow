"""Mask and compositing nodes — pure CPU, no weights.

These are the pieces that make the executor's DAG shape usable from an actual
pipeline rather than only in principle: ``mask_from_image`` / ``load_mask`` give
LaMa (and PowerPaint / FLUX Fill) their second input, and ``blend`` merges two
branches back into one. Both skip the GPU semaphore (``uses_gpu = False``), so
they overlap with GPU work in a wave.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..core.errors import NodeExecutionError
from ..core.ordering import STAGE_MASK
from ..core.types import (
    BaseRestorationNode,
    ImageArray,
    LicenseInfo,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
)
from ..core.weights import default_data_dir

_APACHE = LicenseInfo(
    spdx_id="Apache-2.0",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/ericcayers/Restoration-Workflow/blob/main/LICENSE",
)

SECOND_INPUT = "image_b"
MASK_INPUT = "mask"


class MaskFromImageNode(BaseRestorationNode):
    """Derive a mask from the image's alpha channel, its luminance, or
    automatically-detected physical defects.

    Emitted as a 3-channel greyscale image so that it can be previewed, saved and
    fed anywhere an image is accepted — the engine has exactly one in-memory
    image format and a mask is not a special case of it.
    """

    id = "mask_from_image"
    category = NodeCategory.LEGACY
    pipeline_stage = STAGE_MASK
    display_name = "Mask from image"
    description = (
        "Build an inpainting mask from an alpha channel, a luminance threshold, "
        "or auto-detected scratches/dust."
    )
    license = _APACHE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["alpha", "luma", "defect"],
                "default": "alpha",
                "title": "Mask source",
                "description": (
                    "'alpha' marks transparent pixels as holes to fill. 'luma' "
                    "thresholds brightness. 'defect' auto-detects scratches/dust — "
                    "classical detection, not learned (docs/MODEL_STACK.md)."
                ),
            },
            "threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "title": "Threshold",
                "description": "Used by 'luma' only.",
            },
            "invert": {"type": "boolean", "default": False, "title": "Invert"},
            "dilate": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "title": "Dilate (px)",
                "description": "Grow the mask; helps LaMa cover a subject's fringe "
                               "(or a scratch's soft edge).",
            },
        },
        "additionalProperties": False,
    }

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        source = params.get("source", "alpha")
        threshold = float(params.get("threshold", 0.5))

        if source == "alpha":
            if image.ndim != 3 or image.shape[2] != 4:
                raise NodeExecutionError(
                    self.id,
                    "source is 'alpha' but the image has no alpha channel; use "
                    "source='luma', or supply an RGBA image",
                )
            # Transparent (alpha below threshold) is the region to fill.
            mask = (image[..., 3] < threshold).astype(np.float32)
        elif source == "defect":
            mask = _defect_mask(image[..., :3])
        else:
            rgb = image[..., :3]
            luma = rgb @ np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
            mask = (luma >= threshold).astype(np.float32)

        if bool(params.get("invert", False)):
            mask = 1.0 - mask

        dilate = int(params.get("dilate", 0))
        if dilate > 0:
            mask = _dilate(mask, dilate)

        ctx.report_progress(1.0)
        return np.repeat(mask[..., None], 3, axis=2).astype(np.float32)


class LoadMaskNode(BaseRestorationNode):
    """Load a painted Mask Editor asset, or treat the input image as a mask.

    Studio exports from the Mask Editor set ``mask_id`` to the uploaded asset.
    """

    id = "load_mask"
    category = NodeCategory.MASKING
    pipeline_stage = STAGE_MASK
    display_name = "Load mask"
    description = (
        "Emit a greyscale mask from a Mask Editor asset id, or from the input "
        "image's luminance."
    )
    license = _APACHE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["asset", "input"],
                "default": "asset",
                "title": "Source",
            },
            "mask_id": {
                "type": "string",
                "default": "",
                "title": "Mask asset id",
                "description": "Id returned by POST /api/masks (Mask Editor export).",
            },
            "invert": {"type": "boolean", "default": False, "title": "Invert"},
        },
        "additionalProperties": False,
    }

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        source = params.get("source", "asset")
        if source == "input":
            rgb = image[..., :3]
            luma = rgb @ np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
            mask = np.clip(luma, 0.0, 1.0)
            if bool(params.get("invert", False)):
                mask = 1.0 - mask
            ctx.report_progress(1.0)
            return np.repeat(mask[..., None], 3, axis=2).astype(np.float32)

        mask_id = str(params.get("mask_id") or "").strip()
        if not mask_id:
            raise NodeExecutionError(
                self.id,
                "mask_id is required when source is 'asset' — export a mask from "
                "the Mask Editor, or set source to 'input'",
            )

        masks_dir = _resolve_masks_dir(params, ctx)
        path = masks_dir / f"{mask_id}.png"
        if not path.is_file():
            raise NodeExecutionError(
                self.id,
                f"no mask asset for mask_id={mask_id!r} under {masks_dir}",
            )

        from PIL import Image  # noqa: PLC0415

        with Image.open(path) as img:
            arr = np.asarray(img.convert("L"), dtype=np.float32) / 255.0

        if arr.shape[:2] != image.shape[:2]:
            from PIL import Image as PilImage  # noqa: PLC0415

            resized = PilImage.fromarray((arr * 255).astype(np.uint8), mode="L").resize(
                (image.shape[1], image.shape[0]),
                resample=PilImage.Resampling.NEAREST,
            )
            arr = np.asarray(resized, dtype=np.float32) / 255.0

        if bool(params.get("invert", False)):
            arr = 1.0 - arr

        ctx.report_progress(1.0)
        return np.repeat(arr[..., None], 3, axis=2).astype(np.float32)


def _resolve_masks_dir(params: dict[str, Any], ctx: RunContext) -> Path:
    raw = params.get("masks_dir")
    if raw:
        return Path(str(raw))
    if ctx.data_dir:
        return Path(ctx.data_dir) / "masks"
    return default_data_dir() / "masks"


# Same technique and constants as core/analyzer.py's _defect_score() (kept as a
# separate, self-contained copy rather than importing core.analyzer here — nodes
# only depend on core.types/core.errors, not on the analyzer module) — a
# discrete physical defect (scratch, dust) is a pixel that both deviates
# strongly from a broad local median *and* sits at a near-saturated absolute
# value, which is what separates it from ordinary photo edges/texture.
_DEFECT_MEDIAN_WINDOW = 5
_DEFECT_RESIDUAL_THRESHOLD = 0.15
_DEFECT_EXTREME_LOW = 0.12
_DEFECT_EXTREME_HIGH = 0.88


def _median_filter(gray: ImageArray, size: int) -> ImageArray:
    radius = size // 2
    padded = np.pad(gray, radius, mode="edge")
    stack = np.stack([
        padded[dy:dy + gray.shape[0], dx:dx + gray.shape[1]]
        for dy in range(size) for dx in range(size)
    ])
    return np.median(stack, axis=0)


def _defect_mask(rgb: ImageArray) -> ImageArray:
    luma = rgb @ np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
    residual = np.abs(luma - _median_filter(luma, _DEFECT_MEDIAN_WINDOW))
    extreme = (luma < _DEFECT_EXTREME_LOW) | (luma > _DEFECT_EXTREME_HIGH)
    return (extreme & (residual > _DEFECT_RESIDUAL_THRESHOLD)).astype(np.float32)


def _dilate(mask: ImageArray, radius: int) -> ImageArray:
    """Square-structuring-element dilation via a max over shifts (no cv2 needed)."""
    padded = np.pad(mask, radius, mode="constant", constant_values=0.0)
    h, w = mask.shape
    out = np.zeros_like(mask)
    span = 2 * radius + 1
    for dy in range(span):
        for dx in range(span):
            np.maximum(out, padded[dy : dy + h, dx : dx + w], out=out)
    return out


def defect_mask_rgb(rgb: ImageArray) -> ImageArray:
    """Public helper for Mask Editor scratch detect (returns HxW float)."""
    return _defect_mask(rgb)


class BlendNode(BaseRestorationNode):
    """Merge two branches: ``image`` and ``image_b``.

    This is the node Studio Mode's "run two face models on the same crop and
    blend the results" use case is built from (UI_DESIGN.md section 8), and the
    reason the executor was written as a DAG rather than a chain.

    When a ``mask`` input is connected, mix is weighted per-pixel: masked
    regions pull toward ``image_b`` by ``alpha``.
    """

    id = "blend"
    category = NodeCategory.ORCHESTRATION
    display_name = "Blend"
    description = "Blend two pipeline branches into one image."
    license = _APACHE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "alpha": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "title": "Mix",
                "description": (
                    "0.0 is all of 'image', 1.0 is all of 'image_b'. "
                    "With a mask connected, mix applies only inside the mask."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["normal", "lighten", "darken"],
                "default": "normal",
                "title": "Blend mode",
            },
        },
        "additionalProperties": False,
    }

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        other = ctx.inputs.get(SECOND_INPUT)
        if other is None:
            raise NodeExecutionError(
                self.id,
                f"no '{SECOND_INPUT}' input is connected — blend merges two branches, "
                f"so connect a second node to its '{SECOND_INPUT}' input",
            )
        if other.shape[:2] != image.shape[:2]:
            raise NodeExecutionError(
                self.id,
                f"cannot blend a {other.shape[:2]} image into a {image.shape[:2]} one; "
                f"both branches must end at the same resolution",
            )

        a, b = _match_channels(image, other)
        alpha = float(np.clip(params.get("alpha", 0.5), 0.0, 1.0))
        mode = params.get("mode", "normal")

        if mode == "lighten":
            merged = np.maximum(a, b)
        elif mode == "darken":
            merged = np.minimum(a, b)
        else:
            merged = a * (1.0 - alpha) + b * alpha

        mask = ctx.inputs.get(MASK_INPUT)
        if mask is not None and mode == "normal":
            if mask.ndim == 3:
                m = mask[..., :3].mean(axis=2) if mask.shape[2] >= 3 else mask[..., 0]
            else:
                m = mask
            if m.shape[:2] != image.shape[:2]:
                raise NodeExecutionError(
                    self.id,
                    f"mask is {m.shape[:2]} but the image is {image.shape[:2]}; "
                    f"the mask must match both blend inputs",
                )
            w = np.clip(m.astype(np.float32), 0.0, 1.0)[..., None] * alpha
            merged = a * (1.0 - w) + b * w

        ctx.report_progress(1.0)
        return merged.astype(np.float32)


def _match_channels(a: ImageArray, b: ImageArray) -> tuple[ImageArray, ImageArray]:
    if a.shape[2] == b.shape[2]:
        return a, b
    return a[..., :3], b[..., :3]
