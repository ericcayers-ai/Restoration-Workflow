"""BiRefNet — high-resolution matting (MODEL_STACK.md Phase 2).

MIT-licensed dichotomous segmentation / matting model. Outputs an RGBA image with
a refined alpha matte suitable for compositing and background removal. Weights are
loaded from the author's Hugging Face repo via ``transformers`` (trust_remote_code)
because BiRefNet is not in spandrel's MAIN_REGISTRY.
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
    WeightFile,
)
from ._torch import require_torch, to_numpy, to_tensor

_BIREFNET_LICENSE = LicenseInfo(
    spdx_id="MIT",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://huggingface.co/ZhengPeng7/BiRefNet-matting",
)


class BiRefNetNode(BaseRestorationNode):
    id = "birefnet"
    category = NodeCategory.MASKING
    pipeline_stage = STAGE_MASK
    display_name = "BiRefNet"
    description = (
        "High-resolution matting for hair, fur, and fine edges — outputs RGBA "
        "with a refined alpha channel."
    )
    license = _BIREFNET_LICENSE
    vram_tier = VramTier.MID
    uses_gpu = True
    supports_tiling = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "refine": {
                "type": "boolean",
                "default": True,
                "title": "Refine edges",
                "description": "Apply a light morphological cleanup on the matte.",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="model.safetensors",
            size_bytes=444_000_000,
            sha256="9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154",
            hf_repo_id="ZhengPeng7/BiRefNet-matting",
            hf_filename="model.safetensors",
        ),
    ]

    def __init__(self) -> None:
        self._model: Any = None

    def unload(self) -> None:
        self._model = None
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:  # pragma: no cover
            pass

    def _load_model(self, ctx: RunContext) -> Any:
        if self._model is not None:
            return self._model
        if ctx.weights_dir is None:
            raise NodeExecutionError(self.id, "no weights directory was provided")
        require_torch(self.id)
        node_dir = Path(ctx.weights_dir)
        try:
            from huggingface_hub import snapshot_download  # noqa: PLC0415
            from transformers import AutoModelForImageSegmentation  # noqa: PLC0415
        except ImportError as exc:
            raise NodeExecutionError(
                self.id,
                "BiRefNet requires transformers + huggingface_hub (pip install "
                "restoration-workflow[inference])",
            ) from exc
        if not (node_dir / "config.json").exists():
            snapshot_download(
                "ZhengPeng7/BiRefNet-matting",
                local_dir=str(node_dir),
                local_dir_use_symlinks=False,
            )
        try:
            model = AutoModelForImageSegmentation.from_pretrained(
                str(node_dir),
                trust_remote_code=True,
                local_files_only=True,
            )
        except Exception as exc:
            raise NodeExecutionError(
                self.id,
                f"could not load BiRefNet weights: {exc}",
            ) from exc
        device = ctx.device if ctx.device != "cpu" else "cpu"
        model.to(device).eval()
        self._model = model
        return model

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        import asyncio  # noqa: PLC0415

        return await asyncio.to_thread(self.run_sync, image, params, ctx)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        torch, _ = require_torch(self.id)
        model = self._load_model(ctx)
        rgb = image[..., :3]
        device = next(model.parameters()).device

        x = to_tensor(torch, rgb, str(device), torch.float32)
        ctx.report_progress(0.1)
        ctx.check_cancelled()

        with torch.inference_mode():
            preds = model(x)
            if isinstance(preds, (list, tuple)):
                pred = preds[-1]
            elif hasattr(preds, "logits"):
                pred = preds.logits
            else:
                pred = preds
            if pred.ndim == 4:
                matte = torch.sigmoid(pred[:, 0:1])
            else:
                matte = torch.sigmoid(pred.unsqueeze(1) if pred.ndim == 3 else pred)

        ctx.report_progress(0.9)
        alpha = to_numpy(matte).squeeze()
        if alpha.ndim == 3:
            alpha = alpha[..., 0]
        alpha = np.clip(alpha.astype(np.float32), 0.0, 1.0)

        if bool(params.get("refine", True)):
            alpha = _refine_alpha(alpha)

        rgba = np.concatenate([rgb, alpha[..., None]], axis=2)
        ctx.report_progress(1.0)
        return rgba.astype(np.float32)


def _refine_alpha(alpha: ImageArray) -> ImageArray:
    """Light 3x3 max-pool + blur using numpy only."""
    h, w = alpha.shape
    padded = np.pad(alpha, 1, mode="edge")
    blocks = np.stack(
        [padded[y : y + h, x : x + w] for y in range(3) for x in range(3)],
        axis=0,
    )
    closed = blocks.max(axis=0)
    kernel = np.ones((3, 3), dtype=np.float32) / 9.0
    out = np.zeros_like(closed)
    for y in range(h):
        for x in range(w):
            out[y, x] = (closed[y : y + 3, x : x + 3] * kernel).sum()
    return out
