"""Mask and compositing nodes — pure CPU, no weights.

These are the pieces that make the executor's DAG shape usable from an actual
pipeline rather than only in principle: ``mask_from_image`` gives LaMa its second
input, and ``blend`` merges two branches back into one. Both skip the GPU
semaphore (``uses_gpu = False``), so they overlap with GPU work in a wave.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core.errors import NodeExecutionError
from ..core.types import (
    BaseRestorationNode,
    ImageArray,
    LicenseInfo,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
)

_APACHE = LicenseInfo(
    spdx_id="Apache-2.0",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/ericcayers/Restoration-Workflow/blob/main/LICENSE",
)

SECOND_INPUT = "image_b"


class MaskFromImageNode(BaseRestorationNode):
    """Derive a mask from the image's alpha channel or its luminance.

    Emitted as a 3-channel greyscale image so that it can be previewed, saved and
    fed anywhere an image is accepted — the engine has exactly one in-memory
    image format and a mask is not a special case of it.
    """

    id = "mask_from_image"
    category = NodeCategory.MASKING
    display_name = "Mask from image"
    description = "Build an inpainting mask from an alpha channel or a luminance threshold."
    license = _APACHE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["alpha", "luma"],
                "default": "alpha",
                "title": "Mask source",
                "description": (
                    "'alpha' marks transparent pixels as holes to fill. "
                    "'luma' thresholds brightness."
                ),
            },
            "threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "title": "Threshold",
            },
            "invert": {"type": "boolean", "default": False, "title": "Invert"},
            "dilate": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "title": "Dilate (px)",
                "description": "Grow the mask; helps LaMa cover a subject's fringe.",
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


class BlendNode(BaseRestorationNode):
    """Merge two branches: ``image`` and ``image_b``.

    This is the node Studio Mode's "run two face models on the same crop and
    blend the results" use case is built from (UI_DESIGN.md section 8), and the
    reason the executor was written as a DAG rather than a chain.
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
                "description": "0.0 is all of 'image', 1.0 is all of 'image_b'.",
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

        ctx.report_progress(1.0)
        return merged.astype(np.float32)


def _match_channels(a: ImageArray, b: ImageArray) -> tuple[ImageArray, ImageArray]:
    if a.shape[2] == b.shape[2]:
        return a, b
    return a[..., :3], b[..., :3]
