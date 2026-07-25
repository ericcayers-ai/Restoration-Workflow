"""RealESRGAN — the default general upscaler (MODEL_STACK.md, Regression tier).

Blind super-resolution. Its synthetic degradation model was trained to undo
noise, mild blur and compression alongside the upscale, which is why the rule
table also reaches for it at scale 2 on a noisy but already-large image rather
than shipping a separate denoiser.

Loaded through spandrel's ESRGAN architecture (RealESRGAN's generator is an
RRDBNet); both official checkpoints are BSD-3-Clause.
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
from ._torch import SpandrelNode

_RELEASES = "https://github.com/xinntao/Real-ESRGAN/releases/download"

_FILE_FOR_SCALE = {
    2: "RealESRGAN_x2plus.pth",
    4: "RealESRGAN_x4plus.pth",
}


class RealEsrganNode(SpandrelNode):
    id = "realesrgan"
    category = NodeCategory.REGRESSION
    display_name = "RealESRGAN"
    description = "Blind super-resolution; the default general upscaler."
    license = LicenseInfo(
        spdx_id="BSD-3-Clause",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE",
    )
    vram_tier = VramTier.LOW
    supports_tiling = True
    tags = ["sr"]

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "scale": {
                "type": "integer",
                "enum": [2, 4],
                "default": 4,
                "title": "Upscale factor",
            },
            "tile": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "title": "Tile size",
                "description": "0 disables tiling. Set automatically on GPU out-of-memory.",
            },
            "tile_pad": {
                "type": "integer",
                "minimum": 0,
                "default": 32,
                "title": "Tile context padding",
                "description": "Extra context given to each tile and then discarded. "
                               "Too small and tile seams become visible.",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="RealESRGAN_x4plus.pth",
            size_bytes=67040989,
            sha256="4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
            url=f"{_RELEASES}/v0.1.0/RealESRGAN_x4plus.pth",
        ),
        WeightFile(
            filename="RealESRGAN_x2plus.pth",
            size_bytes=67061725,
            sha256="49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb",
            url=f"{_RELEASES}/v0.2.1/RealESRGAN_x2plus.pth",
        ),
    ]

    def weight_filename(self, params: dict[str, Any]) -> str:
        scale = int(params.get("scale", 4))
        return _FILE_FOR_SCALE.get(scale, _FILE_FOR_SCALE[4])

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return self._run_descriptor(image, params, ctx)
