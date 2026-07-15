"""InstructIR — Master Restorer (MIT, marcosv/InstructIR on Hugging Face).

Natural-language instruction-guided restoration. Studio Advanced Mode's Master
Restorer: preset or freeform prompts, optional ensemble guidance modes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..core.analyzer import DegradationProfile
from ..core.ensemble import VALID_ENSEMBLE_MODES
from ..core.errors import PipelineValidationError
from ..core.highlight import soft_blend_masked
from ..core.instruction import list_prompt_presets, prompt_by_id
from ..core.ordering import STAGE_INSTRUCT
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

# Frozen sentence encoder used by InstructIR's LM head (MIT / Apache-2.0 upstream).
# Managed through the normal weight download path — not a silent Hub fetch at run.
_TEXT_ENCODER_DIR = "bge-micro-v2"
_TEXT_ENCODER_FILES = (
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/config.json",
        size_bytes=745,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="config.json",
    ),
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/model.safetensors",
        size_bytes=34_785_664,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="model.safetensors",
    ),
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/tokenizer.json",
        size_bytes=711_661,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="tokenizer.json",
    ),
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/tokenizer_config.json",
        size_bytes=1_564,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="tokenizer_config.json",
    ),
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/special_tokens_map.json",
        size_bytes=228,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="special_tokens_map.json",
    ),
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/vocab.txt",
        size_bytes=231_508,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="vocab.txt",
    ),
    WeightFile(
        filename=f"{_TEXT_ENCODER_DIR}/added_tokens.json",
        size_bytes=82,
        sha256=None,
        hf_repo_id="TaylorAI/bge-micro-v2",
        hf_filename="added_tokens.json",
    ),
)


def _prompt_enum() -> list[str]:
    ids = [p["id"] for p in list_prompt_presets()]
    return ["custom"] + ids


def _default_instruction() -> str:
    preset = prompt_by_id("instruct_only_general")
    if preset:
        return str(preset["instruction"])
    return "Restore this photograph: reduce noise, blur, and compression artifacts."


class InstructIrNode(BaseRestorationNode):
    id = "instructir"
    category = NodeCategory.INSTRUCT
    pipeline_stage = STAGE_INSTRUCT
    display_name = "InstructIR"
    description = (
        "Master Restorer — instruction-guided restoration (MIT). "
        "Guides specialist ensembles via preset or freeform prompts, "
        "with an optional finish pass."
    )
    license = LicenseInfo(
        spdx_id="MIT",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/mv-lab/InstructIR/blob/main/LICENSE.md",
    )
    vram_tier = VramTier.MID
    uses_gpu = True
    supports_tiling = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt_preset": {
                "type": "string",
                "enum": _prompt_enum(),
                "default": "instruct_only_general",
                "title": "Prompt preset",
                "description": "Named instruction from the Master Restorer library.",
            },
            "instruction": {
                "type": "string",
                "default": _default_instruction(),
                "title": "Custom instruction",
                "description": "Freeform text; wins when edited away from the preset.",
            },
            "mode": {
                "type": "string",
                "enum": sorted(VALID_ENSEMBLE_MODES),
                "default": "finish_only",
                "title": "Master mode",
                "description": (
                    "finish_only: run as polish pass; instruct_only: InstructIR alone; "
                    "guide_and_finish: conductor builds specialists then finishes "
                    "(this node still runs the InstructIR pass)."
                ),
            },
            "strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 1.0,
                "title": "Strength",
            },
            "mask_highlights": {
                "type": "boolean",
                "default": False,
                "title": "Mask highlights",
                "description": (
                    "Soft-blend the InstructIR result only inside the clipped-highlight "
                    "mask so unclipped midtones are preserved."
                ),
            },
            "clip_threshold": {
                "type": "number",
                "minimum": 0.8,
                "maximum": 1.0,
                "default": 0.97,
                "title": "Clip mask threshold",
            },
        },
        "additionalProperties": False,
    }

    weight_manifest = [
        WeightFile(
            filename="im_instructir-7d.pt",
            size_bytes=63_627_895,
            sha256="f28d8f0f66ff57449ebe2be52241dfdd53a3dfab1003d63e65493f96ea152fd0",
            hf_repo_id="marcosv/InstructIR",
            hf_filename="im_instructir-7d.pt",
        ),
        WeightFile(
            filename="lm_instructir-7d.pt",
            size_bytes=403_275,
            sha256="b239e5d5dbc811813a90e709f9647dead0e35a96a294a7d6c5263da549016fe6",
            hf_repo_id="marcosv/InstructIR",
            hf_filename="lm_instructir-7d.pt",
        ),
        *_TEXT_ENCODER_FILES,
    ]

    def __init__(self) -> None:
        self._runtime_cache: dict[str, Any] = {}

    def unload(self) -> None:
        self._runtime_cache.clear()
        try:
            import torch  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            return
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return await asyncio.to_thread(self.run_sync, image, params, ctx)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        from .inference.instructir_runtime import run_instructir  # noqa: PLC0415

        resolved = dict(params)
        mode = str(resolved.get("mode") or "finish_only")
        if mode not in VALID_ENSEMBLE_MODES:
            raise PipelineValidationError(
                f"invalid InstructIR mode {mode!r}; expected one of "
                f"{sorted(VALID_ENSEMBLE_MODES)}"
            )

        preset_id = str(resolved.get("prompt_preset") or "")
        instruction = str(resolved.get("instruction") or "").strip()
        preset = prompt_by_id(preset_id) if preset_id and preset_id != "custom" else None
        if preset and (
            not instruction
            or instruction == self.param_schema["properties"]["instruction"]["default"]
            or instruction == preset.get("instruction")
        ):
            resolved["instruction"] = preset["instruction"]
        elif not instruction and preset:
            resolved["instruction"] = preset["instruction"]

        # Highlight rescue presets mask by default unless explicitly disabled.
        if preset_id == "blown_highlight_rescue" and "mask_highlights" not in params:
            resolved["mask_highlights"] = True

        if ctx.weights_dir is None:
            raise PipelineValidationError("InstructIR requires an installed weights directory")

        weights_dir = Path(ctx.weights_dir)
        restored = run_instructir(
            image,
            resolved,
            ctx,
            weights_dir=weights_dir,
            cache=self._runtime_cache,
            text_encoder_dir=weights_dir / _TEXT_ENCODER_DIR,
        )

        if bool(resolved.get("mask_highlights")):
            ctx.check_cancelled()
            threshold = float(resolved.get("clip_threshold", 0.97))
            mask = DegradationProfile.clip_mask(image, threshold=threshold)
            restored = soft_blend_masked(image, restored, mask, feather=0.12)
            ctx.report_progress(1.0, "highlight-masked blend")

        return restored

    def restore_with_instruction(
        self,
        image: ImageArray,
        instruction: str,
        params: dict[str, Any],
        ctx: RunContext,
    ) -> ImageArray:
        merged = {**params, "instruction": instruction}
        return self.run_sync(image, merged, ctx)
