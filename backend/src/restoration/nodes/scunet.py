"""SCUNet — practical blind denoising (MODEL_STACK.md, Regression tier).

SCUNet ("Swin-Conv-UNet", Zhang et al.) is a real-world *blind* denoiser: unlike
the fixed-sigma SwinIR denoise models, it was trained against a practical
degradation model (noise + camera ISP + JPEG), so it takes no noise-level
parameter and generalises to photographs and scans whose noise you can't
characterise up front. That makes it the robust denoise stage in Simple Mode's
default chain, ahead of the face and upscale stages so they don't amplify grain.

Two checkpoints ship, both from the original author's KAIR release and both
Apache-2.0:

* ``scunet_color_real_gan``  — GAN-trained, better perceptual quality on real
  photos (the default here).
* ``scunet_color_real_psnr`` — PSNR-optimised, more conservative; preferred when
  fidelity matters more than apparent sharpness.

Loaded through spandrel's SCUNet architecture; the checkpoints are a bare state
dict, so no transform is needed.
"""

from __future__ import annotations

from typing import Any

from ..core.ordering import STAGE_DENOISE
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

_KAIR_RELEASE = "https://github.com/cszn/KAIR/releases/download/v1.0"

_FILE_FOR_VARIANT = {
    "gan": "scunet_color_real_gan.pth",
    "psnr": "scunet_color_real_psnr.pth",
}


class ScunetNode(SpandrelNode):
    id = "scunet"
    category = NodeCategory.LEGACY
    pipeline_stage = STAGE_DENOISE
    display_name = "SCUNet"
    description = "Blind real-world denoising; robust when the noise level is unknown."
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/cszn/SCUNet/blob/main/LICENSE",
    )
    vram_tier = VramTier.LOW
    supports_tiling = True

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "variant": {
                "type": "string",
                "enum": ["gan", "psnr"],
                "default": "gan",
                "title": "Variant",
                "description": (
                    "'gan' restores more apparent detail on real photos; 'psnr' is "
                    "more conservative and truer to the input."
                ),
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
                "description": "Extra context given to each tile and then discarded.",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="scunet_color_real_gan.pth",
            size_bytes=71982835,
            sha256="892c83f812c59173273b74f4f34a14ecaf57a2fdb68df056664589beb55c966e",
            url=f"{_KAIR_RELEASE}/scunet_color_real_gan.pth",
        ),
        WeightFile(
            filename="scunet_color_real_psnr.pth",
            size_bytes=71982841,
            sha256="fa78899ba2caec9d235a900e91d96c689da71c42029230c2028b00f09f809c2e",
            url=f"{_KAIR_RELEASE}/scunet_color_real_psnr.pth",
        ),
    ]

    def weight_filename(self, params: dict[str, Any]) -> str:
        variant = str(params.get("variant", "gan"))
        return _FILE_FOR_VARIANT.get(variant, _FILE_FOR_VARIANT["gan"])

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return self._run_descriptor(image, params, ctx)
