"""LaMa — fast large-mask inpainting (MODEL_STACK.md, Masking tier).

LaMa is the only in-box node that takes a second input: it fills the region a
``mask`` marks. Wire a mask into its ``mask`` input (``mask_from_image`` is the
in-box way to produce one); the pipeline's primary image goes to ``image``.

Weight sourcing needs an explanation, because the obvious source doesn't work.
Upstream (advimman/lama, Apache-2.0) distributes ``big-lama.zip`` containing a
PyTorch Lightning checkpoint, and the widely-mirrored ``big-lama.pt`` is a
TorchScript archive. Neither is usable here: the Lightning checkpoint embeds
pickled trainer objects and is therefore rejected by ``weights_only=True``
loading, and a TorchScript archive is code, not a state dict. This node uses a
``safetensors`` export of the same generator weights instead — a format that
cannot carry executable content at all — with its digest pinned below. The
licence is upstream's; only the container changed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core.errors import NodeExecutionError
from ..core.ordering import STAGE_INPAINT
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

MASK_INPUT = "mask"


def _generator_only(state_dict: dict) -> dict:
    """Keep the generator; drop the discriminator and loss weights the export
    also carries. spandrel rewrites the ``generator.`` prefix itself, but its
    ``load_state_dict`` is strict, so anything else must go first."""
    return {k: v for k, v in state_dict.items() if k.startswith("generator.")}


class LamaNode(SpandrelNode):
    id = "lama"
    category = NodeCategory.MASKING
    pipeline_stage = STAGE_INPAINT
    display_name = "LaMa"
    description = "Fast large-mask inpainting and object removal."
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/advimman/lama/blob/main/LICENSE",
    )
    vram_tier = VramTier.LOW
    # Inpainting a tile at a time destroys the global context that makes LaMa's
    # fourier convolutions work on large holes. Better to fail with the
    # executor's lower-tier suggestion than to return a seam-ridden fill.
    supports_tiling = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "mask_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "title": "Mask threshold",
                "description": "Mask values above this are treated as holes to fill.",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="big-lama.safetensors",
            size_bytes=496800380,
            sha256="f8fcaae73ca8a96e463bf29c7583ea84a3c99075cb58ff90ceed6816243a1f09",
            hf_repo_id="4bit/big-lama",
            hf_filename="big-lama.safetensors",
        ),
    ]

    state_dict_transform = staticmethod(_generator_only)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        mask = ctx.inputs.get(MASK_INPUT)
        if mask is None:
            raise NodeExecutionError(
                self.id,
                "no mask input is connected — LaMa fills the region a mask marks, "
                "so connect a mask-producing node (e.g. 'mask_from_image') to its "
                "'mask' input",
            )

        rgb, alpha = split_alpha(image)
        mask_gray = _as_mask(mask, rgb.shape[:2], self.id)
        binary = (mask_gray >= float(params.get("mask_threshold", 0.5))).astype(np.float32)
        if not binary.any():
            ctx.report_progress(1.0, "mask is empty; image passed through unchanged")
            return image

        torch, _ = require_torch(self.id)
        desc = self.descriptor(ctx, params)

        x = to_tensor(torch, rgb, str(desc.device), desc.dtype)
        m = to_tensor(torch, binary[..., None], str(desc.device), desc.dtype)

        ctx.report_progress(0.1, "inpainting")
        out = infer(desc, x, mask=m, on_progress=ctx.report_progress,
                    check_cancel=ctx.check_cancelled)
        filled = to_numpy(out)

        # LaMa reconstructs the whole frame; keep the original pixels outside the
        # mask so an unrelated part of the photo is never quietly rewritten.
        keep = binary[..., None]
        composited = filled * keep + rgb * (1.0 - keep)
        return merge_alpha(composited.astype(np.float32), alpha)


def _as_mask(mask: ImageArray, shape: tuple[int, int], node_id: str) -> ImageArray:
    """Reduce whatever came down the mask edge to a single-channel HxW float map."""
    if mask.ndim == 3:
        mask = mask[..., :3].mean(axis=2) if mask.shape[2] >= 3 else mask[..., 0]
    if mask.shape[:2] != shape:
        raise NodeExecutionError(
            node_id,
            f"mask is {mask.shape[:2]} but the image is {shape}; the mask must be "
            f"produced from the same image (do not upscale one and not the other)",
        )
    return np.clip(mask.astype(np.float32), 0.0, 1.0)
