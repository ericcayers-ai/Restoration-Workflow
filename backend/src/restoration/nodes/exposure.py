"""Exposure recovery — classical (non-learned) local tone mapping for
over/under-exposed detail loss (MODEL_STACK.md, ROADMAP.md Phase 4.5.1).

Research finding (2026-07-12): no learned exposure-correction model clears
this repo's bar for a default/auto-download node. The one serious permissive
candidate, RetinexFormer (MIT, spandrel-native), has no GitHub-release weight
source — Google Drive/Baidu only, the same disqualifying pattern already
established for HAT. Rather than relax that bar for convenience, this node
ships a classical technique instead: an automatic gamma pass (moves the
image's own mean luma toward middle grey, clamped so an already-well-exposed
photo is left alone) followed by CLAHE (Contrast Limited Adaptive Histogram
Equalization) on the perceptual lightness channel — the same family of
techniques real photo-editing tools use for exposure and local
shadow/highlight recovery. Gamma alone would restore overall brightness but
not local detail; CLAHE alone recovers local detail but not overall
brightness — the combination does both. It recovers *compressed dynamic
range that's still present in the file* — it does not hallucinate detail
that was never captured, and should never be described as if it does.

No weights, no GPU — this is why it runs first in the restoration order
(``STAGE_EXPOSURE``, before deblocking/denoising/upscaling): correcting
exposure before those stages means they see, and don't have to compensate
for, a properly-exposed image.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core.errors import InferenceUnavailableError
from ..core.ordering import STAGE_EXPOSURE
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


def _require_cv2(node_id: str) -> Any:
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:
        raise InferenceUnavailableError(node_id) from exc
    return cv2


class ExposureCorrectNode(BaseRestorationNode):
    id = "exposure_correct"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_EXPOSURE
    display_name = "Exposure Correct"
    description = (
        "Recovers shadow and highlight detail via adaptive local contrast "
        "enhancement (CLAHE) — classical, not learned."
    )
    license = _APACHE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []
    tags = ["exposure"]

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "clip_limit": {
                "type": "number",
                "minimum": 0.5,
                "maximum": 8.0,
                "default": 2.5,
                "title": "Clip limit",
                "description": "Higher recovers more local detail but risks visible "
                               "haloing/noise amplification in flat regions.",
            },
            "tile_grid": {
                "type": "integer",
                "minimum": 2,
                "maximum": 16,
                "default": 8,
                "title": "Tile grid size",
                "description": "The image is divided into an NxN grid; each tile gets "
                               "its own local contrast curve.",
            },
            "strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 1.0,
                "title": "Strength",
                "description": "Blend between the original (0) and fully corrected (1) "
                               "result — a safety valve against over-processing.",
            },
        },
        "additionalProperties": False,
    }

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        cv2 = _require_cv2(self.id)

        rgb = image[..., :3] if image.ndim == 3 and image.shape[2] == 4 else image
        alpha = image[..., 3] if image.ndim == 3 and image.shape[2] == 4 else None

        rgb_clipped = np.clip(rgb, 0.0, 1.0)

        # Dual-tone path: lift shadows and gently compress highlights separately
        # so blown regions get a soft recovery curve without washing midtones.
        luma = (
            0.2126 * rgb_clipped[..., 0]
            + 0.7152 * rgb_clipped[..., 1]
            + 0.0722 * rgb_clipped[..., 2]
        )
        shadow_mask = np.clip((0.35 - luma) / 0.35, 0.0, 1.0)[..., None]
        highlight_mask = np.clip((luma - 0.70) / 0.30, 0.0, 1.0)[..., None]
        # Soft highlight rolloff (preserves remaining detail near clip).
        highlight_soft = np.power(np.clip(rgb_clipped, 0, 1), 1.25)
        shadow_lift = np.power(np.clip(rgb_clipped, 1e-6, 1), 0.75)
        tone_mapped = (
            rgb_clipped * (1.0 - shadow_mask) * (1.0 - highlight_mask * 0.5)
            + shadow_lift * shadow_mask
            + highlight_soft * highlight_mask * 0.5
        )
        tone_mapped = np.clip(tone_mapped, 0.0, 1.0)

        mean_luma = float(tone_mapped.mean())
        gamma = 1.0
        if 1e-4 < mean_luma < 1.0 - 1e-4:
            gamma = float(np.clip(np.log(0.5) / np.log(mean_luma), 0.35, 3.0))
        gamma_corrected = np.power(tone_mapped, gamma)

        rgb_u8 = (gamma_corrected * 255.0 + 0.5).astype(np.uint8)

        lab = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB)
        light, a_ch, b_ch = cv2.split(lab)

        clip_limit = float(params.get("clip_limit", 2.5))
        tile_grid = int(params.get("tile_grid", 8))
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
        light_corrected = clahe.apply(light)

        lab_corrected = cv2.merge([light_corrected, a_ch, b_ch])
        rgb_corrected = cv2.cvtColor(lab_corrected, cv2.COLOR_LAB2RGB)

        corrected = rgb_corrected.astype(np.float32) / 255.0
        strength = float(np.clip(params.get("strength", 1.0), 0.0, 1.0))
        blended = rgb_clipped * (1.0 - strength) + corrected * strength

        ctx.report_progress(1.0)
        if alpha is not None:
            return np.concatenate([blended, alpha[..., None]], axis=2).astype(np.float32)
        return blended.astype(np.float32)
