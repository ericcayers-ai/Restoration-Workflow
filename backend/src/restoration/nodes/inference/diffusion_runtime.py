"""Diffusion-tier restoration via diffusers (PowerPaint, DiffBIR, SUPIR, FLUX Fill)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np

from ...core.errors import InferenceUnavailableError, NodeExecutionError
from ...core.types import ImageArray, RunContext
from .._torch import (
    _DEFAULT_TILE_PAD,
    infer,
    load_descriptor,
    merge_alpha,
    require_torch,
    split_alpha,
    to_numpy,
    to_tensor,
)


def _require_diffusers(node_id: str) -> Any:
    try:
        import diffusers  # noqa: PLC0415
    except ImportError as exc:
        raise InferenceUnavailableError(node_id) from exc
    return diffusers


def _pil_from_array(image: ImageArray):
    from PIL import Image  # noqa: PLC0415

    arr = (np.clip(image, 0, 1) * 255).astype(np.uint8)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    return Image.fromarray(arr)


def _array_from_pil(img) -> ImageArray:
    arr = np.asarray(img).astype(np.float32) / 255.0
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    return arr[:, :, :3]


def run_diffusion_restore(
    node_id: str,
    image: ImageArray,
    params: dict[str, Any],
    ctx: RunContext,
    *,
    mode: Literal["inpaint", "restore", "fill"],
    weights_dir: Path,
    hf_repo: str | None = None,
    local_filename: str | None = None,
) -> ImageArray:
    """Best-effort diffusion inference using diffusers pipelines."""
    torch, _ = require_torch(node_id)
    _require_diffusers(node_id)
    device = ctx.device
    steps = int(params.get("steps", 20))
    strength = float(params.get("strength", 0.35))
    dtype = torch.float16 if "cuda" in device else torch.float32

    pil = _pil_from_array(image)

    if mode == "fill" and hf_repo:
        from diffusers import FluxFillPipeline  # noqa: PLC0415

        pipe = FluxFillPipeline.from_pretrained(hf_repo, torch_dtype=dtype)
        pipe = pipe.to(device)
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.float32)
        mask_pil = _pil_from_array(np.stack([mask] * 3, axis=-1))
        result = pipe(
            prompt=params.get("prompt", "high quality photograph"),
            image=pil,
            mask_image=mask_pil,
            num_inference_steps=steps,
            guidance_scale=float(params.get("guidance", 3.5)),
        ).images[0]
        return _array_from_pil(result)

    if mode == "inpaint":
        from diffusers import AutoPipelineForInpainting  # noqa: PLC0415

        model_id = hf_repo or "runwayml/stable-diffusion-inpainting"
        pipe = AutoPipelineForInpainting.from_pretrained(
            model_id,
            torch_dtype=dtype,
            safety_checker=None,
        )
        pipe = pipe.to(device)
        w, h = pil.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask_pil = _pil_from_array(np.stack([mask] * 3, axis=-1))
        result = pipe(
            prompt=params.get("prompt", "clean photograph"),
            image=pil,
            mask_image=mask_pil,
            num_inference_steps=steps,
            strength=strength,
        ).images[0]
        return _array_from_pil(result)

    from diffusers import StableDiffusionImg2ImgPipeline  # noqa: PLC0415

    model_id = hf_repo or "runwayml/stable-diffusion-v1-5"
    pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        safety_checker=None,
    )
    pipe = pipe.to(device)
    result = pipe(
        prompt=params.get("prompt", "high quality sharp photograph, detailed"),
        image=pil,
        strength=min(0.55, strength),
        num_inference_steps=steps,
    ).images[0]
    return _array_from_pil(result)


def run_spandrel_checkpoint(
    node_id: str,
    image: ImageArray,
    params: dict[str, Any],
    ctx: RunContext,
    *,
    weights_dir: Path,
    filename: str,
) -> ImageArray:
    """Load a checkpoint through spandrel when the architecture is supported."""
    torch, _ = require_torch(node_id)
    path = weights_dir / filename
    if not path.is_file():
        raise NodeExecutionError(node_id, f"weights not found: {filename}")
    desc = load_descriptor(node_id, path)
    desc.to(torch.device(ctx.device)).eval()
    rgb, alpha = split_alpha(image)
    x = to_tensor(torch, rgb, ctx.device, desc.dtype)
    out = infer(
        desc,
        x,
        tile=int(params.get("tile") or 0),
        pad=int(params.get("tile_pad") or _DEFAULT_TILE_PAD),
        on_progress=ctx.report_progress,
        check_cancel=ctx.check_cancelled,
    )
    return merge_alpha(to_numpy(out), alpha)
