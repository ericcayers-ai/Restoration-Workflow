"""DDColor — automatic colourization (Apache-2.0, piddnad/DDColor via spandrel)."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core.ordering import STAGE_COLORIZE
from ..core.types import (
    ImageArray,
    LicenseInfo,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
    WeightFile,
)
from ._torch import (
    SpandrelNode,
    infer,
    merge_alpha,
    require_torch,
    split_alpha,
    to_numpy,
    to_tensor,
)

_VARIANT_FILES = {
    "modelscope": "ddcolor_modelscope.pth",
    "artistic": "ddcolor_artistic.pth",
    "paper": "ddcolor_paper.pth",
}


class DdColorNode(SpandrelNode):
    id = "ddcolor"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_COLORIZE
    display_name = "DDColor"
    description = (
        "Automatic colourization for grayscale / near-mono photos "
        "(Apache-2.0, ConvNeXt + decoder)."
    )
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/piddnad/DDColor/blob/master/LICENSE",
    )
    vram_tier = VramTier.MID
    supports_tiling = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "variant": {
                "type": "string",
                "enum": ["modelscope", "artistic", "paper"],
                "default": "modelscope",
                "title": "Variant",
                "description": "'modelscope' is the balanced default; 'artistic' is punchier.",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="ddcolor_modelscope.pth",
            size_bytes=935_000_000,
            sha256=None,
            hf_repo_id="piddnad/DDColor-models",
            hf_filename="ddcolor_modelscope.pth",
        ),
        WeightFile(
            filename="ddcolor_artistic.pth",
            size_bytes=935_000_000,
            sha256=None,
            hf_repo_id="piddnad/DDColor-models",
            hf_filename="ddcolor_artistic.pth",
        ),
        WeightFile(
            filename="ddcolor_paper.pth",
            size_bytes=870_000_000,
            sha256=None,
            hf_repo_id="piddnad/DDColor-models",
            hf_filename="ddcolor_paper.pth",
        ),
    ]

    def weight_filename(self, params: dict[str, Any]) -> str:
        variant = str(params.get("variant", "modelscope"))
        return _VARIANT_FILES.get(variant, _VARIANT_FILES["modelscope"])

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        """DDColor's spandrel call expects a single-channel luma tensor."""
        torch, _ = require_torch(self.id)
        desc = self.descriptor(ctx, params)
        rgb, alpha = split_alpha(image)
        luma = (
            0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        ).astype(np.float32)
        x = to_tensor(torch, luma[..., None], str(desc.device), desc.dtype)
        out = infer(
            desc,
            x,
            tile=0,
            on_progress=ctx.report_progress,
            check_cancel=ctx.check_cancelled,
        )
        return merge_alpha(to_numpy(out), alpha)
