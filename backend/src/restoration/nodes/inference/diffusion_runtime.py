"""Diffusion-tier restoration via diffusers (PowerPaint, SUPIR, FLUX Fill)."""

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

_TILE_THRESHOLD = 768
_TILE_OVERLAP = 64
_MASK_INPUT = "mask"


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


def _local_weight_path(weights_dir: Path, filename: str | None) -> Path | None:
    if not filename:
        return None
    path = weights_dir / filename
    return path if path.is_file() else None


def resolve_inpaint_mask(
    node_id: str,
    image: ImageArray,
    ctx: RunContext,
    *,
    require_nonzero: bool = False,
) -> ImageArray:
    """Return a single-channel HxW float mask from ``ctx.inputs['mask']``.

    PowerPaint / FLUX Fill previously synthesised an all-zero mask, which made
    the inpaint path a no-op. Callers must wire a real mask edge.
    """
    mask = ctx.inputs.get(_MASK_INPUT)
    if mask is None:
        raise NodeExecutionError(
            node_id,
            "no mask input is connected — inpainting fills the region a mask marks, "
            "so connect a mask-producing node (e.g. 'load_mask' or 'mask_from_image') "
            f"to its '{_MASK_INPUT}' input",
        )
    if mask.ndim == 3:
        mask = mask[..., :3].mean(axis=2) if mask.shape[2] >= 3 else mask[..., 0]
    shape = image.shape[:2]
    if mask.shape[:2] != shape:
        raise NodeExecutionError(
            node_id,
            f"mask is {mask.shape[:2]} but the image is {shape}; the mask must be "
            f"produced from the same image",
        )
    out = np.clip(mask.astype(np.float32), 0.0, 1.0)
    if require_nonzero and not bool(out.any()):
        raise NodeExecutionError(
            node_id,
            "mask is empty (all zeros) — paint or generate a region to inpaint before running",
        )
    return out


def _mask_to_pil(mask: ImageArray):
    """Greyscale PIL mask; white = fill region for diffusers inpaint."""
    from PIL import Image  # noqa: PLC0415

    arr = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def _run_tiled_pil(
    pil,
    runner,
    *,
    tile: int,
    overlap: int = _TILE_OVERLAP,
    mask_pil=None,
):
    """Run a PIL→PIL callable over overlapping tiles for large images."""
    w, h = pil.size
    if max(w, h) <= tile:
        return runner(pil, mask_pil.resize(pil.size) if mask_pil is not None else None)

    from PIL import Image  # noqa: PLC0415

    counts = np.zeros((h, w), dtype=np.float32)
    accum = np.zeros((h, w, 3), dtype=np.float32)
    step = max(tile - overlap, tile // 2)

    for y in range(0, h, step):
        for x in range(0, w, step):
            x1, y1 = min(x + tile, w), min(y + tile, h)
            x0, y0 = max(0, x1 - tile), max(0, y1 - tile)
            crop = pil.crop((x0, y0, x1, y1))
            crop_mask = mask_pil.crop((x0, y0, x1, y1)) if mask_pil is not None else None
            restored = runner(crop, crop_mask)
            arr = np.asarray(restored, dtype=np.float32)
            accum[y0:y1, x0:x1] += arr
            counts[y0:y1, x0:x1] += 1.0

    blended = (accum / np.maximum(counts[..., None], 1.0)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(blended)


def _hf_token() -> str | None:
    import os  # noqa: PLC0415

    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def _load_img2img_pipe(node_id: str, model_id: str, device: str, dtype: Any):
    from diffusers import StableDiffusionImg2ImgPipeline  # noqa: PLC0415

    pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        safety_checker=None,
        token=_hf_token(),
    )
    return pipe.to(device)


def _run_powerpaint_inpaint(
    node_id: str,
    pil,
    mask_pil,
    params: dict[str, Any],
    *,
    device: str,
    dtype: Any,
    weights_dir: Path,
    hf_repo: str | None,
    steps: int,
    strength: float,
):
    """Inpaint via PowerPaint BrushNet when weights are present, else SD inpainting."""
    brushnet = _local_weight_path(weights_dir, "powerpaint_brushnet.safetensors")
    if brushnet is not None and hf_repo:
        try:
            from diffusers import (  # noqa: PLC0415
                BrushNetModel,
                StableDiffusionBrushNetPipeline,
            )

            brush = BrushNetModel.from_pretrained(
                hf_repo,
                subfolder="PowerPaint_Brushnet",
                torch_dtype=dtype,
                local_files_only=False,
            )
            pipe = StableDiffusionBrushNetPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                brushnet=brush,
                torch_dtype=dtype,
                safety_checker=None,
            )
            pipe = pipe.to(device)
        except Exception:
            brushnet = None

    if brushnet is None:
        from diffusers import AutoPipelineForInpainting  # noqa: PLC0415

        model_id = hf_repo or "runwayml/stable-diffusion-inpainting"
        pipe = AutoPipelineForInpainting.from_pretrained(
            model_id,
            torch_dtype=dtype,
            safety_checker=None,
        )
        pipe = pipe.to(device)

    return pipe(
        prompt=params.get("prompt", "clean photograph"),
        image=pil,
        mask_image=mask_pil,
        num_inference_steps=steps,
        strength=strength,
    ).images[0]


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
    tile = int(params.get("tile") or 0) or _TILE_THRESHOLD

    pil = _pil_from_array(image)

    if mode == "fill" and hf_repo:
        from diffusers import FluxFillPipeline  # noqa: PLC0415

        try:
            pipe = FluxFillPipeline.from_pretrained(
                hf_repo, torch_dtype=dtype, token=_hf_token()
            )
        except Exception as exc:
            raise NodeExecutionError(
                node_id,
                "FLUX Fill requires a Hugging Face token with gated-model access "
                "(set HF_TOKEN) and the [diffusion] extra.",
            ) from exc
        pipe = pipe.to(device)
        mask = resolve_inpaint_mask(node_id, image, ctx, require_nonzero=True)
        mask_pil = _mask_to_pil(mask)
        h, w = image.shape[:2]

        def _fill(crop, crop_mask):
            return pipe(
                prompt=params.get("prompt", "high quality photograph"),
                image=crop,
                mask_image=crop_mask if crop_mask is not None else mask_pil.resize(crop.size),
                num_inference_steps=steps,
                guidance_scale=float(params.get("guidance", 3.5)),
            ).images[0]

        result = (
            _run_tiled_pil(pil, _fill, tile=tile, mask_pil=mask_pil)
            if max(w, h) > tile
            else _fill(pil, mask_pil)
        )
        return _array_from_pil(result)

    if mode == "inpaint":
        mask = resolve_inpaint_mask(node_id, image, ctx, require_nonzero=True)
        mask_pil = _mask_to_pil(mask)
        result = _run_powerpaint_inpaint(
            node_id,
            pil,
            mask_pil,
            params,
            device=device,
            dtype=dtype,
            weights_dir=weights_dir,
            hf_repo=hf_repo,
            steps=steps,
            strength=strength,
        )
        return _array_from_pil(result)

    # restore: prefer local checkpoint via spandrel when the architecture is known.
    local = _local_weight_path(weights_dir, local_filename)
    if local is not None:
        try:
            return run_spandrel_checkpoint(
                node_id,
                image,
                params,
                ctx,
                weights_dir=weights_dir,
                filename=local_filename or local.name,
            )
        except NodeExecutionError as exc:
            # SUPIR's published ckpt is not a generic SD/img2img weight — do not
            # fall through to from_pretrained on a non-diffusers Hub mirror.
            if node_id == "supir":
                raise NodeExecutionError(
                    node_id,
                    "Downloaded SUPIR-v0Q.ckpt is present but the full SUPIR "
                    "architecture is not yet vendored for inference. The weight "
                    f"file is at {local}.",
                ) from exc

    model_id = hf_repo or "runwayml/stable-diffusion-v1-5"
    try:
        pipe = _load_img2img_pipe(node_id, model_id, device, dtype)
    except Exception as exc:
        raise NodeExecutionError(
            node_id,
            "Diffusion restore requires Hugging Face access for the model repo "
            f"({model_id}). Set HF_TOKEN if the repo is gated.",
        ) from exc

    prompt = params.get("prompt", "high quality sharp photograph, detailed")
    eff_strength = min(0.55, strength)

    def _restore(crop, _crop_mask=None):
        return pipe(
            prompt=prompt,
            image=crop,
            strength=eff_strength,
            num_inference_steps=steps,
        ).images[0]

    w, h = pil.size
    result = (
        _run_tiled_pil(pil, _restore, tile=tile)
        if max(w, h) > tile
        else _restore(pil)
    )
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
