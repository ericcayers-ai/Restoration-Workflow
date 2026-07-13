"""MambaIRv2 super-resolution runtime (csguoh/MambaIR, Apache-2.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.errors import InferenceUnavailableError, NodeExecutionError
from ...core.types import ImageArray, RunContext
from .._torch import merge_alpha, require_torch, split_alpha, to_numpy, to_tensor


def _build_mambair(scale: int = 4):
    from ..vendored.mambairv2_arch import MambaIRv2  # noqa: PLC0415

    return MambaIRv2(
        img_size=64,
        patch_size=1,
        in_chans=3,
        embed_dim=48,
        depths=(5, 5, 5, 5),
        num_heads=(4, 4, 4, 4),
        window_size=16,
        mlp_ratio=2.0,
        qkv_bias=True,
        drop_rate=0.0,
        attn_drop_rate=0.0,
        drop_path_rate=0.1,
        norm_layer=None,
        ape=False,
        patch_norm=True,
        use_checkpoint=False,
        upscale=scale,
        img_range=1.0,
        upsampler="pixelshuffle",
        resi_connection="1conv",
    )


def run_mambair(
    image: ImageArray,
    params: dict[str, Any],
    ctx: RunContext,
    *,
    weights_dir: Path,
    model_filename: str,
) -> ImageArray:
    torch, _ = require_torch("mambair")
    try:
        import einops  # noqa: F401, PLC0415
        import mamba_ssm  # noqa: F401, PLC0415
    except ImportError as exc:
        raise InferenceUnavailableError("mambair") from exc

    device = torch.device(ctx.device)
    path = weights_dir / model_filename
    if not path.is_file():
        raise NodeExecutionError("mambair", f"weights not found: {path.name}")

    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "params" in state:
        state = state["params"]
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]

    model = _build_mambair(scale=4)
    model.load_state_dict(state, strict=False)
    model.to(device)
    model.eval()

    rgb, alpha = split_alpha(image)
    tensor = to_tensor(torch, rgb, ctx.device, torch.float32)
    with torch.inference_mode():
        out = model(tensor)
    restored = merge_alpha(to_numpy(out), alpha)
    return restored
