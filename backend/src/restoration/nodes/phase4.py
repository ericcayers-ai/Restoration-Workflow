"""Phase 4 license-gated and diffusion restoration nodes (MODEL_STACK.md)."""

from __future__ import annotations

import asyncio
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

_SCAFFOLD_SHA = {
    "gpen": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "osdface": "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
    "powerpaint": "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01",
    "diffbir": "3456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef012",
    "supir": "456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123",
    "flux": "56789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234",
}


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
            size_bytes=348_127_232,
            sha256=_SCAFFOLD_SHA["gpen"],
            url="https://github.com/yangxy/GPEN/releases/download/v1.0/GPEN-BFR-512.pth",
        ),
        YUNET_WEIGHT,
    ]

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        raise NodeExecutionError(
            self.id,
            "GPEN checkpoint integration is scaffolded — spandrel does not "
            "include the GPEN architecture. Download weights via Manage Downloads; "
            "full inference ships when the reference pipeline is vendored.",
        )


# ---------------------------------------------------------------------------
# OSDFace (unclear licence — opt-in with acknowledgement)
# ---------------------------------------------------------------------------


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
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="osdface.pth",
            size_bytes=500_000_000,
            sha256=_SCAFFOLD_SHA["osdface"],
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
        raise NodeExecutionError(
            self.id,
            "OSDFace integration is scaffolded pending upstream licence "
            "verification. See docs/MODEL_STACK.md — contact the author before "
            "using in production.",
        )


# ---------------------------------------------------------------------------
# Diffusion scaffold base
# ---------------------------------------------------------------------------


class DiffusionScaffoldNode(BaseRestorationNode):
    """Shared scaffold for diffusion-tier nodes awaiting full vendored inference."""

    uses_gpu = True
    supports_tiling = True

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
        },
        "additionalProperties": False,
    }

    _upstream_module: str = ""
    _upstream_hint: str = ""

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return await asyncio.to_thread(self.run_sync, image, params, ctx)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        try:
            return self._run_upstream(image, params, ctx)
        except ImportError:
            raise NodeExecutionError(
                self.id,
                f"{self.display_name} requires the optional diffusion stack. "
                f"{self._upstream_hint}",
            ) from None

    def _run_upstream(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        raise NodeExecutionError(
            self.id,
            f"{self.display_name} upstream module ({self._upstream_module}) is not "
            "yet vendored in this release. Weights can be downloaded and the node "
            "appears in the model stack; full inference ships when the reference "
            "pipeline is integrated. Track ROADMAP.md Phase 4.",
        )


class PowerPaintNode(DiffusionScaffoldNode):
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
    _upstream_module = "powerpaint"
    _upstream_hint = "pip install restoration-workflow[diffusion] when available."

    weight_manifest = [
        WeightFile(
            filename="powerpaint_v2.safetensors",
            size_bytes=2_000_000_000,
            sha256=_SCAFFOLD_SHA["powerpaint"],
            hf_repo_id="JunhaoZhuang/PowerPaint-v2-1",
            hf_filename="PowerPaint/pytorch_model.bin",
        ),
    ]


class DiffBirNode(DiffusionScaffoldNode):
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
    _upstream_module = "diffbir"
    _upstream_hint = "See ComfyUI-DiffBIR for reference weights."

    weight_manifest = [
        WeightFile(
            filename="diffbir_v2.pt",
            size_bytes=3_500_000_000,
            sha256=_SCAFFOLD_SHA["diffbir"],
            url="https://github.com/XPixelGroup/DiffBIR/releases/download/v2.0/DiffBIR_v2.pt",
        ),
    ]


class SupirNode(DiffusionScaffoldNode):
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
    _upstream_module = "supir"
    _upstream_hint = "Requires ~24GB VRAM (fp8: <10GB)."

    weight_manifest = [
        WeightFile(
            filename="SUPIR-v0Q.ckpt",
            size_bytes=5_000_000_000,
            sha256=_SCAFFOLD_SHA["supir"],
            hf_repo_id="Fanghua-Yu/SUPIR",
            hf_filename="SUPIR-v0Q.ckpt",
        ),
    ]


class FluxFillNode(DiffusionScaffoldNode):
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
    _upstream_module = "flux"
    _upstream_hint = "Accept FLUX non-commercial licence on Hugging Face first."

    weight_manifest = [
        WeightFile(
            filename="flux1-fill-dev.safetensors",
            size_bytes=12_000_000_000,
            sha256=_SCAFFOLD_SHA["flux"],
            hf_repo_id="black-forest-labs/FLUX.1-Fill-dev",
            hf_filename="flux1-fill-dev.safetensors",
        ),
    ]
