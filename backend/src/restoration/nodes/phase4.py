"""Phase 4 license-gated and diffusion restoration nodes (MODEL_STACK.md)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..core.errors import NodeExecutionError
from ..core.ordering import STAGE_FACE, STAGE_INPAINT, STAGE_UPSCALE
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
from .face_nodes import YUNET_WEIGHT, FaceRestorationNode
from .inference.diffusion_runtime import run_diffusion_restore, run_spandrel_checkpoint
from .inference.gpen_runtime import run_gpen


class GpenNode(FaceRestorationNode):
    id = "gpen"
    display_name = "GPEN"
    description = (
        "GAN prior embedded network for severely degraded high-res faces; "
        "non-commercial (Alibaba academic licence)."
    )
    license = LicenseInfo(
        spdx_id="Alibaba-Academic",
        kind=LicenseKind.NON_COMMERCIAL,
        source_url="https://github.com/yangxy/GPEN",
    )
    vram_tier = VramTier.MID
    model_filename = "GPEN-BFR-512.pth"
    weight_manifest = [
        WeightFile(
            filename="GPEN-BFR-512.pth",
            size_bytes=284_085_738,
            sha256="f1002c41add95b0decad69604d80455576f7187dd99ca16bd611bcfd44c10b51",
            hf_repo_id="akhaliq/GPEN-BFR-512",
            hf_filename="GPEN-BFR-512.pth",
        ),
        YUNET_WEIGHT,
    ]

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        weights_dir = Path(ctx.weights_dir)
        return run_gpen(
            image,
            params,
            ctx,
            weights_dir=weights_dir,
            model_filename=self.model_filename,
        )


class OsdFaceNode(BaseRestorationNode):
    id = "osdface"
    category = NodeCategory.FACE
    pipeline_stage = STAGE_FACE
    display_name = "OSDFace"
    description = (
        "One-step diffusion face restoration at GAN speed. Licence unverified — "
        "opt-in only until confirmed with the upstream author."
    )
    license = LicenseInfo(
        spdx_id="Unverified",
        kind=LicenseKind.UNCLEAR,
        source_url="https://github.com/jkwang28/OSDFace",
    )
    vram_tier = VramTier.HIGH
    uses_gpu = True
    supports_tiling = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 1.0,
                "title": "Restoration strength",
            },
            "steps": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 15,
                "title": "Diffusion steps",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="osdface.pth",
            size_bytes=500_000_000,
            sha256=None,
            hf_repo_id="jkwang28/OSDFace",
            hf_filename="osdface.pth",
        ),
    ]

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return await asyncio.to_thread(self.run_sync, image, params, ctx)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        weights_dir = Path(ctx.weights_dir)
        try:
            return run_spandrel_checkpoint(
                self.id, image, params, ctx, weights_dir=weights_dir, filename="osdface.pth"
            )
        except NodeExecutionError:
            return run_diffusion_restore(
                self.id,
                image,
                params,
                ctx,
                mode="restore",
                weights_dir=weights_dir,
                hf_repo="runwayml/stable-diffusion-v1-5",
            )


class DiffusionNode(BaseRestorationNode):
    """Shared base for diffusion-tier nodes using diffusers."""

    uses_gpu = True
    supports_tiling = True
    _mode: str = "restore"
    _hf_repo: str | None = None
    _local_weight: str | None = None

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tile": {
                "type": "integer",
                "minimum": 0,
                "default": 512,
                "title": "Tile size",
            },
            "steps": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 20,
                "title": "Diffusion steps",
            },
            "strength": {
                "type": "number",
                "minimum": 0.05,
                "maximum": 1.0,
                "default": 0.35,
                "title": "Denoise strength",
            },
            "prompt": {
                "type": "string",
                "default": "high quality photograph, sharp, detailed",
                "title": "Prompt",
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
        if self._local_weight:
            try:
                return run_spandrel_checkpoint(
                    self.id,
                    image,
                    params,
                    ctx,
                    weights_dir=weights_dir,
                    filename=self._local_weight,
                )
            except NodeExecutionError:
                pass
        return run_diffusion_restore(
            self.id,
            image,
            params,
            ctx,
            mode=self._mode,  # type: ignore[arg-type]
            weights_dir=weights_dir,
            hf_repo=self._hf_repo,
            local_filename=self._local_weight,
        )


class PowerPaintNode(DiffusionNode):
    id = "powerpaint"
    category = NodeCategory.MASKING
    pipeline_stage = STAGE_INPAINT
    display_name = "PowerPaint"
    description = "Text-guided inpaint/removal/outpaint (SD1.5-based, MIT licence)."
    license = LicenseInfo(
        spdx_id="MIT",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/open-mmlab/PowerPaint",
    )
    vram_tier = VramTier.MID
    _mode = "inpaint"
    _hf_repo = "JunhaoZhuang/PowerPaint-v2-1"

    weight_manifest = [
        WeightFile(
            filename="powerpaint_brushnet.safetensors",
            size_bytes=3_544_366_408,
            sha256="530f2886ef5bcdf199269ec344155a517639ba64219b85eeb23fd86aab93147f",
            hf_repo_id="JunhaoZhuang/PowerPaint-v2-1",
            hf_filename="PowerPaint_Brushnet/diffusion_pytorch_model.safetensors",
        ),
    ]


class DiffBirNode(DiffusionNode):
    id = "diffbir"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_UPSCALE
    display_name = "DiffBIR"
    description = (
        "Blind image restoration via diffusion; general/background pre-stage "
        "(Apache-2.0)."
    )
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/XPixelGroup/DiffBIR",
    )
    vram_tier = VramTier.HIGH
    _mode = "restore"
    _local_weight = "diffbir_v2.pt"

    weight_manifest = [
        WeightFile(
            filename="diffbir_v2.pt",
            size_bytes=3_500_000_000,
            sha256=None,
            url="https://huggingface.co/ai-forever/DiffBIR-v2/resolve/main/DiffBIR_v2.pt",
        ),
    ]


class SupirNode(DiffusionNode):
    id = "supir"
    category = NodeCategory.GENERATIVE
    pipeline_stage = STAGE_UPSCALE
    display_name = "SUPIR"
    description = "Best-in-class generative upscale/restoration (non-commercial)."
    license = LicenseInfo(
        spdx_id="SUPIR-NC",
        kind=LicenseKind.NON_COMMERCIAL,
        source_url="https://github.com/Fanghua-Yu/SUPIR",
    )
    vram_tier = VramTier.VERY_HIGH
    _mode = "restore"
    _hf_repo = "Fanghua-Yu/SUPIR"

    weight_manifest = [
        WeightFile(
            filename="SUPIR-v0Q.ckpt",
            size_bytes=5_000_000_000,
            sha256=None,
            hf_repo_id="Fanghua-Yu/SUPIR",
            hf_filename="SUPIR-v0Q.ckpt",
        ),
    ]


class FluxFillNode(DiffusionNode):
    id = "flux_fill"
    category = NodeCategory.GENERATIVE
    pipeline_stage = STAGE_INPAINT
    display_name = "FLUX Fill"
    description = "FLUX.1-Fill text-guided inpaint/outpaint (non-commercial)."
    license = LicenseInfo(
        spdx_id="FLUX-NC",
        kind=LicenseKind.NON_COMMERCIAL,
        source_url="https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev",
    )
    vram_tier = VramTier.VERY_HIGH
    _mode = "fill"
    _hf_repo = "black-forest-labs/FLUX.1-Fill-dev"

    weight_manifest = [
        WeightFile(
            filename="flux1-fill-dev.safetensors",
            size_bytes=23_804_922_408,
            sha256=None,
            hf_repo_id="black-forest-labs/FLUX.1-Fill-dev",
            hf_filename="flux1-fill-dev.safetensors",
        ),
    ]
