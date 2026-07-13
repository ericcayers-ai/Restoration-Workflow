"""Old-photo scratch restoration — classical CV (ROADMAP.md 4.5.2 follow-up)."""

from __future__ import annotations

import asyncio
from typing import Any

from ..core.ordering import STAGE_INPAINT
from ..core.types import (
    BaseRestorationNode,
    ImageArray,
    LicenseInfo,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
)
from .inference.classical_scratch import restore_scratches

_MIT = LicenseInfo(
    spdx_id="Apache-2.0",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/ericcayers-ai/Restoration-Workflow",
)


class OldPhotosScratchNode(BaseRestorationNode):
    id = "old_photos_scratch"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_INPAINT
    display_name = "Old photo scratch restore"
    description = (
        "Classical scratch and dust removal via morphological detection and "
        "OpenCV inpainting. Inspired by old-photo restoration workflows; not the "
        "learned Microsoft Bringing-Old-Photos model."
    )
    license = _MIT
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "kernel": {
                "type": "integer",
                "minimum": 5,
                "maximum": 51,
                "default": 15,
                "title": "Scratch kernel length",
            },
            "threshold": {
                "type": "integer",
                "minimum": 5,
                "maximum": 80,
                "default": 25,
                "title": "Detection threshold",
            },
            "radius": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 3,
                "title": "Inpaint radius",
            },
            "method": {
                "type": "string",
                "enum": ["telea", "ns"],
                "default": "telea",
                "title": "Inpaint method",
            },
        },
        "additionalProperties": False,
    }

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return await asyncio.to_thread(self.run_sync, image, params, ctx)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return restore_scratches(image, params)
