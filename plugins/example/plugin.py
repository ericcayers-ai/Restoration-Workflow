"""Example third-party plugin — inverts colours (Phase 6 acceptance demo)."""

from __future__ import annotations

from typing import Any

import numpy as np

from restoration.core.types import (
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
    source_url="https://github.com/ericcayers-ai/Restoration-Workflow",
)


class InvertNode(BaseRestorationNode):
    id = "example_invert"
    category = NodeCategory.ORCHESTRATION
    display_name = "Invert (example plugin)"
    description = "Demonstrates the plugin SDK — inverts RGB channels."
    license = _APACHE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest: list = []
    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        ctx.report_progress(1.0)
        rgb = image[..., :3]
        out = 1.0 - rgb
        if image.shape[-1] == 4:
            return np.concatenate([out, image[..., 3:4]], axis=2).astype(np.float32)
        return out.astype(np.float32)
