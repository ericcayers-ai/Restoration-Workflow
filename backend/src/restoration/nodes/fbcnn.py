"""FBCNN — flexible blind JPEG artifact removal (MODEL_STACK.md, Regression tier).

FBCNN's distinguishing feature over a fixed JPEG denoiser is that the quality
factor it restores *toward* is an input, not a constant: the network predicts
the image's QF and you may override that prediction to trade artifact removal
against detail retention. spandrel's default call path throws the QF away, so
this node calls the underlying module directly when the user pins one.

The convention comes from the reference implementation (``main_test_fbcnn.py``):
the network's internal quality embedding is ``1 - QF/100``, so a *lower*
requested quality factor drives *stronger* restoration.
"""

from __future__ import annotations

from typing import Any

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
    _DEFAULT_TILE_PAD,
    SpandrelNode,
    descriptor_scale,
    infer,
    merge_alpha,
    require_torch,
    split_alpha,
    to_numpy,
    to_tensor,
)


class FbcnnNode(SpandrelNode):
    id = "fbcnn"
    category = NodeCategory.REGRESSION
    display_name = "FBCNN"
    description = "Adjustable-strength JPEG compression artifact removal."
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/jiaxi-jiang/FBCNN/blob/main/LICENSE",
    )
    vram_tier = VramTier.LOW
    supports_tiling = True

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "quality_factor": {
                "type": ["integer", "null"],
                "minimum": 1,
                "maximum": 100,
                "default": None,
                "title": "Quality factor",
                "description": (
                    "JPEG quality to restore toward. Leave empty to use the "
                    "quality factor FBCNN predicts from the image itself. "
                    "Lower values restore more aggressively and smooth more detail."
                ),
            },
            "tile": {"type": "integer", "minimum": 0, "default": 0, "title": "Tile size"},
            "tile_pad": {
                "type": "integer",
                "minimum": 0,
                "default": 32,
                "title": "Tile context padding",
                "description": "Extra context given to each tile and then discarded.",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="fbcnn_color.pth",
            size_bytes=287755111,
            sha256="8b0e4ef23d59cf7ac934a342cb31a17619e4fa4a0b3374a9d78c5174312387e8",
            url="https://github.com/jiaxi-jiang/FBCNN/releases/download/v1.0/fbcnn_color.pth",
        ),
    ]

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        qf = params.get("quality_factor")
        if qf is None:
            # Predicted-QF path: spandrel's own call_fn already returns out[0].
            return self._run_descriptor(image, params, ctx)

        torch, _ = require_torch(self.id)
        desc = self.descriptor(ctx, params)
        rgb, alpha = split_alpha(image)
        x = to_tensor(torch, rgb, str(desc.device), desc.dtype)

        qf_tensor = torch.tensor(
            [[1.0 - float(qf) / 100.0]], device=desc.device, dtype=desc.dtype
        )
        out = infer(
            _PinnedQf(torch, desc, qf_tensor),
            x,
            tile=int(params.get("tile") or 0),
            pad=int(params.get("tile_pad") or _DEFAULT_TILE_PAD),
            on_progress=ctx.report_progress,
            check_cancel=ctx.check_cancelled,
        )
        return merge_alpha(to_numpy(out), alpha)


class _PinnedQf:
    """Presents ``model(x, qf)`` through the same surface ``infer()`` drives on a
    spandrel descriptor: callable, plus scale/size/channel metadata."""

    def __init__(self, torch: Any, descriptor: Any, qf_tensor: Any) -> None:
        self._torch = torch
        self._descriptor = descriptor
        self._qf = qf_tensor
        self.scale = descriptor_scale(descriptor)
        self.size_requirements = descriptor.size_requirements
        self.output_channels = descriptor.output_channels

    def __call__(self, patch: Any) -> Any:
        with self._torch.inference_mode():
            return self._descriptor.model(patch, self._qf)[0]
