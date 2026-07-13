"""Phase 4 stretch-tier restoration nodes (MODEL_STACK.md)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..core.ordering import STAGE_DENOISE, STAGE_UPSCALE
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
from .inference.diffusion_runtime import run_diffusion_restore, run_spandrel_checkpoint

_APACHE = LicenseInfo(
    spdx_id="Apache-2.0",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/csguoh/MambaIR",
)

_MIT = LicenseInfo(
    spdx_id="MIT",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/unirestore/UniRestore",
)


class StretchNode(BaseRestorationNode):
    uses_gpu = True
    supports_tiling = True
    _hf_repo: str | None = None
    _weight_name: str = ""
    _use_mambair = False
    _use_diffusion = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tile": {"type": "integer", "minimum": 0, "default": 512, "title": "Tile size"},
            "steps": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 20,
                "title": "Diffusion steps",
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
        weights_dir = Path(ctx.weights_dir)
        if self._use_mambair:
            from .inference.mambair_runtime import run_mambair  # noqa: PLC0415

            return run_mambair(
                image,
                params,
                ctx,
                weights_dir=weights_dir,
                model_filename=self._weight_name,
            )
        if self._use_diffusion:
            return run_diffusion_restore(
                self.id,
                image,
                params,
                ctx,
                mode="restore",
                weights_dir=weights_dir,
                hf_repo=self._hf_repo,
                local_filename=self._weight_name,
            )
        return run_spandrel_checkpoint(
            self.id,
            image,
            params,
            ctx,
            weights_dir=weights_dir,
            filename=self._weight_name,
        )


class MambaIrNode(StretchNode):
    id = "mambair"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_UPSCALE
    display_name = "MambaIRv2"
    description = "Efficient SOTA super-resolution (Mamba architecture, Apache-2.0)."
    license = _APACHE
    vram_tier = VramTier.MID
    _use_mambair = True
    _weight_name = "mambairv2_classicSR_Small_x4.pth"

    weight_manifest = [
        WeightFile(
            filename="mambairv2_classicSR_Small_x4.pth",
            size_bytes=40_073_223,
            sha256="374d91798ffd901b76504068b5bcb47ea58cba9b8f889ac627428c3c34f3545d",
            url="https://github.com/csguoh/MambaIR/releases/download/v1.0/mambairv2_classicSR_Small_x4.pth",
        ),
    ]


class DarkIrNode(StretchNode):
    id = "darkir"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_DENOISE
    display_name = "DarkIR"
    description = (
        "All-in-one low-light/noise/blur restoration (v1 only). Licence unverified — "
        "opt-in. Weights via Hugging Face (set HF_TOKEN if gated)."
    )
    license = LicenseInfo(
        spdx_id="Unverified",
        kind=LicenseKind.UNCLEAR,
        source_url="https://github.com/cidautai/DarkIR",
    )
    vram_tier = VramTier.LOW
    _weight_name = "darkir_l.pth"

    weight_manifest = [
        WeightFile(
            filename="darkir_l.pth",
            size_bytes=50_000_000,
            sha256=None,
            hf_repo_id="cidautai/DarkIR",
            hf_filename="darkir_l.pth",
        ),
    ]


class InstantIrNode(StretchNode):
    id = "instantir"
    category = NodeCategory.GENERATIVE
    display_name = "InstantIR"
    description = "Blind restoration + creative mode (SDXL RAIL++-M base restrictions apply)."
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/instantX-research/InstantIR",
    )
    vram_tier = VramTier.HIGH
    _use_diffusion = True
    _hf_repo = "instantX-research/InstantIR"
    _weight_name = "instantir.safetensors"

    weight_manifest = [
        WeightFile(
            filename="instantir.safetensors",
            size_bytes=6_000_000_000,
            sha256=None,
            hf_repo_id="instantX-research/InstantIR",
            hf_filename="instantir.safetensors",
        ),
    ]


class DreamClearNode(StretchNode):
    id = "dreamclear"
    category = NodeCategory.GENERATIVE
    display_name = "DreamClear"
    description = (
        "Degradation-routed DiT restoration (PixArt-α base — verify licence). "
        "Requires Hugging Face access to shallowdream204/DreamClear."
    )
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/shallowdream204/DreamClear",
    )
    vram_tier = VramTier.VERY_HIGH
    _use_diffusion = True
    _hf_repo = "shallowdream204/DreamClear"
    _weight_name = "DreamClear-1024.pth"

    weight_manifest = [
        WeightFile(
            filename="DreamClear-1024.pth",
            size_bytes=4_000_000_000,
            sha256=None,
            hf_repo_id="shallowdream204/DreamClear",
            hf_filename="DreamClear-1024.pth",
        ),
    ]


class UniRestoreNode(StretchNode):
    id = "unirestore"
    category = NodeCategory.REGRESSION
    display_name = "UniRestore"
    description = (
        "Unified perceptual + task-oriented restoration (MIT). "
        "Weights via Hugging Face unirestore/UniRestore."
    )
    license = _MIT
    vram_tier = VramTier.MID
    _weight_name = "unirestore.pth"
    _hf_repo = "unirestore/UniRestore"

    weight_manifest = [
        WeightFile(
            filename="unirestore.pth",
            size_bytes=200_000_000,
            sha256=None,
            hf_repo_id="unirestore/UniRestore",
            hf_filename="unirestore.pth",
        ),
    ]


class RealRestorerNode(StretchNode):
    id = "realrestorer"
    category = NodeCategory.GENERATIVE
    display_name = "RealRestorer"
    description = (
        "Blind restoration across 9 degradations (~34GB VRAM). Experimental/opt-in."
    )
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.UNCLEAR,
        source_url="https://github.com/yfyang007/RealRestorer",
    )
    vram_tier = VramTier.VERY_HIGH
    _use_diffusion = True
    _hf_repo = "yfyang007/RealRestorer"
    _weight_name = "realrestorer.pth"

    weight_manifest = [
        WeightFile(
            filename="realrestorer.pth",
            size_bytes=8_000_000_000,
            sha256=None,
            hf_repo_id="yfyang007/RealRestorer",
            hf_filename="realrestorer.pth",
        ),
    ]
