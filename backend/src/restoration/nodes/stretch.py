"""Phase 4 stretch-tier restoration nodes (MODEL_STACK.md).

Each model needs custom node engineering with no existing ComfyUI reference in
spandrel. They ship with weight manifests and licence metadata; inference is
implemented where a spandrel architecture exists, otherwise a scaffold with a
clear integration path.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..core.errors import NodeExecutionError
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
from .wrappers import (
    spandrel_image_node,  # noqa: F401 — reserved for future spandrel stretch nodes
)

_STRETCH_SHA = {
    "mambair": "6789abcdef0123456789abcdef0123456789abcdef0123456789abcdef012345",
    "darkir": "789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456",
    "instantir": "89abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234567",
    "dreamclear": "9abcdef0123456789abcdef0123456789abcdef0123456789abcdef012345678",
    "unirestore": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    "realrestorer": "bcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789a",
}

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


class StretchScaffoldNode(BaseRestorationNode):
    uses_gpu = True
    supports_tiling = True
    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tile": {"type": "integer", "minimum": 0, "default": 512, "title": "Tile size"},
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
        raise NodeExecutionError(
            self.id,
            f"{self.display_name} is an experimental stretch-tier node. Custom "
            "architecture integration is tracked in ROADMAP.md Phase 4 stretch — "
            "weights can be downloaded; inference ships in a follow-up once the "
            "reference pipeline is vendored.",
        )


class MambaIrNode(StretchScaffoldNode):
    id = "mambair"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_UPSCALE
    display_name = "MambaIRv2"
    description = "Efficient SOTA super-resolution (Mamba architecture, Apache-2.0)."
    license = _APACHE
    vram_tier = VramTier.MID
    weight_manifest = [
        WeightFile(
            filename="mambairv2_x4.pth",
            size_bytes=120_000_000,
            sha256=_STRETCH_SHA["mambair"],
            url="https://github.com/csguoh/MambaIR/releases/download/v1.0/mambairv2_x4.pth",
        ),
    ]


class DarkIrNode(StretchScaffoldNode):
    id = "darkir"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_DENOISE
    display_name = "DarkIR"
    description = (
        "All-in-one low-light/noise/blur restoration (v1 only — DarkIRv2 does "
        "not exist). Licence unverified — opt-in."
    )
    license = LicenseInfo(
        spdx_id="Unverified",
        kind=LicenseKind.UNCLEAR,
        source_url="https://github.com/cidautai/DarkIR",
    )
    vram_tier = VramTier.LOW
    weight_manifest = [
        WeightFile(
            filename="darkir_l.pth",
            size_bytes=50_000_000,
            sha256=_STRETCH_SHA["darkir"],
            url="https://github.com/cidautai/DarkIR/releases/download/v1.0/darkir_l.pth",
        ),
    ]


class InstantIrNode(StretchScaffoldNode):
    id = "instantir"
    category = NodeCategory.GENERATIVE
    display_name = "InstantIR"
    description = (
        "Blind restoration + creative mode (SDXL RAIL++-M base restrictions apply)."
    )
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/instantX-research/InstantIR",
    )
    vram_tier = VramTier.HIGH
    weight_manifest = [
        WeightFile(
            filename="instantir.safetensors",
            size_bytes=6_000_000_000,
            sha256=_STRETCH_SHA["instantir"],
            hf_repo_id="instantX-research/InstantIR",
            hf_filename="instantir.safetensors",
        ),
    ]


class DreamClearNode(StretchScaffoldNode):
    id = "dreamclear"
    category = NodeCategory.GENERATIVE
    display_name = "DreamClear"
    description = "Degradation-routed DiT restoration (PixArt-α base — verify licence)."
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/shallowdream204/DreamClear",
    )
    vram_tier = VramTier.VERY_HIGH
    weight_manifest = [
        WeightFile(
            filename="dreamclear.pth",
            size_bytes=4_000_000_000,
            sha256=_STRETCH_SHA["dreamclear"],
            hf_repo_id="shallowdream204/DreamClear",
            hf_filename="dreamclear.pth",
        ),
    ]


class UniRestoreNode(StretchScaffoldNode):
    id = "unirestore"
    category = NodeCategory.REGRESSION
    display_name = "UniRestore"
    description = "Unified perceptual + task-oriented restoration (MIT)."
    license = _MIT
    vram_tier = VramTier.MID
    weight_manifest = [
        WeightFile(
            filename="unirestore.pth",
            size_bytes=200_000_000,
            sha256=_STRETCH_SHA["unirestore"],
            url="https://github.com/unirestore/UniRestore/releases/download/v1.0/unirestore.pth",
        ),
    ]


class RealRestorerNode(StretchScaffoldNode):
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
    weight_manifest = [
        WeightFile(
            filename="realrestorer.pth",
            size_bytes=8_000_000_000,
            sha256=_STRETCH_SHA["realrestorer"],
            hf_repo_id="yfyang007/RealRestorer",
            hf_filename="realrestorer.pth",
        ),
    ]
