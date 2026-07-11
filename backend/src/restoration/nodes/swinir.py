"""SwinIR — one transformer backbone, three restoration tasks (MODEL_STACK.md).

SwinIR (Liang et al., Apache-2.0) is a strong, well-precedented image-restoration
transformer whose official checkpoints cover several distinct tasks with the same
architecture family. spandrel detects the exact hyper-parameters from each
checkpoint, so the three nodes below differ only in which weights they load:

* ``swinir``          — real-world super-resolution (the SwinIR-L x4 GAN model),
  the higher-quality (slower) alternative to RealESRGAN for the upscale stage.
* ``swinir_denoise``  — fixed-level colour denoising, for when you know roughly
  how noisy the source is (SCUNet is the blind, no-knob default; this is the
  Studio knob).
* ``swinir_jpeg``     — colour JPEG artifact reduction at a chosen quality, the
  transformer counterpart to FBCNN.

All weights come from the author's own GitHub release and are Apache-2.0.

A note on the state dict: these checkpoints are stored three different ways —
the L-x4 model wraps its weights under ``params_ema``, the denoise/CAR models
under ``params``, and the M-x2 model is a bare state dict. ``_swinir_weights``
unwraps whichever is present so spandrel's architecture detector sees the bare
encoder keys, and it stays a pure tensor read (``weights_only`` / safetensors).
"""

from __future__ import annotations

from typing import Any

from ..core.ordering import STAGE_ARTIFACT, STAGE_DENOISE, STAGE_UPSCALE
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

_RELEASE = "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0"

_SWINIR_LICENSE = LicenseInfo(
    spdx_id="Apache-2.0",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/JingyunLiang/SwinIR/blob/main/LICENSE",
)


def _swinir_weights(state_dict: dict) -> dict:
    """Return the bare model weights regardless of how the checkpoint wrapped them.

    Official SwinIR checkpoints variously nest the weights under ``params_ema``
    (the EMA copy, preferred when present), ``params``, or store them bare. This
    only ever selects a sub-dict — it never unpickles anything.
    """
    for key in ("params_ema", "params", "state_dict", "model"):
        inner = state_dict.get(key)
        if isinstance(inner, dict):
            return inner
    return state_dict


class SwinIrSrNode(SpandrelNode):
    id = "swinir"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_UPSCALE
    display_name = "SwinIR"
    description = (
        "Transformer super-resolution; higher-quality, slower alternative to "
        "RealESRGAN for the upscale stage."
    )
    license = _SWINIR_LICENSE
    vram_tier = VramTier.MID
    supports_tiling = True
    state_dict_transform = staticmethod(_swinir_weights)

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "scale": {
                "type": "integer",
                "enum": [2, 4],
                "default": 4,
                "title": "Upscale factor",
                "description": "x4 uses the large model; x2 uses the medium model.",
            },
            "tile": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "title": "Tile size",
                "description": "0 disables tiling. Set automatically on GPU out-of-memory. "
                               "SwinIR benefits from tiling on large images.",
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
            filename="003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth",
            size_bytes=142473939,
            sha256="99adfa91350a84c99e946c1eb3d8fce34bc28f57d807b09dc8fe40a316328c0a",
            url=f"{_RELEASE}/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth",
        ),
        WeightFile(
            filename="003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth",
            size_bytes=66974517,
            sha256="f397408977a3e07eb06afb7238d453a12ef35ebab7328a54241f307860dbe342",
            url=f"{_RELEASE}/003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth",
        ),
    ]

    def weight_filename(self, params: dict[str, Any]) -> str:
        scale = int(params.get("scale", 4))
        if scale == 2:
            return "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth"
        return "003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth"

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return self._run_descriptor(image, params, ctx)


class SwinIrDenoiseNode(SpandrelNode):
    id = "swinir_denoise"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_DENOISE
    display_name = "SwinIR Denoise"
    description = "Transformer colour denoising at a fixed noise level."
    license = _SWINIR_LICENSE
    vram_tier = VramTier.MID
    supports_tiling = True
    state_dict_transform = staticmethod(_swinir_weights)

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tile": {"type": "integer", "minimum": 0, "default": 0, "title": "Tile size"},
            "tile_pad": {
                "type": "integer",
                "minimum": 0,
                "default": 32,
                "title": "Tile context padding",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth",
            size_bytes=122905743,
            sha256="39e264322ba762682de5acee4705aaeda7077b947204b9ce1899519ebd540724",
            url=f"{_RELEASE}/005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth",
        ),
    ]

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return self._run_descriptor(image, params, ctx)


class SwinIrJpegNode(SpandrelNode):
    id = "swinir_jpeg"
    category = NodeCategory.REGRESSION
    pipeline_stage = STAGE_ARTIFACT
    display_name = "SwinIR JPEG"
    description = "Transformer JPEG-artifact reduction (alternative to FBCNN)."
    license = _SWINIR_LICENSE
    vram_tier = VramTier.MID
    supports_tiling = True
    state_dict_transform = staticmethod(_swinir_weights)

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tile": {"type": "integer", "minimum": 0, "default": 0, "title": "Tile size"},
            "tile_pad": {
                "type": "integer",
                "minimum": 0,
                "default": 32,
                "title": "Tile context padding",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="006_colorCAR_DFWB_s126w7_SwinIR-M_jpeg20.pth",
            size_bytes=102873665,
            sha256="1b47fa32f358630e3de3430c91296535a0011b16f0518dacd5b847f123023d45",
            url=f"{_RELEASE}/006_colorCAR_DFWB_s126w7_SwinIR-M_jpeg20.pth",
        ),
    ]

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return self._run_descriptor(image, params, ctx)
