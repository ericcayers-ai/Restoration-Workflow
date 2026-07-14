"""GPEN face restoration runtime (yangxy/GPEN, non-commercial weights)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.errors import InferenceUnavailableError, NodeExecutionError
from ...core.types import ImageArray, RunContext
from .._faces import (
    FACE_SIZE,
    YUNET_FILENAME,
    align_face,
    detect_faces,
    paste_face,
    select_faces,
)
from .._torch import merge_alpha, require_torch, split_alpha, to_numpy, to_tensor


def run_gpen(
    image: ImageArray,
    params: dict[str, Any],
    ctx: RunContext,
    *,
    weights_dir: Path,
    model_filename: str,
) -> ImageArray:
    torch, _ = require_torch("gpen")
    try:
        from ..vendored.gpen_model import FullGenerator  # noqa: PLC0415
    except ImportError as exc:
        raise InferenceUnavailableError("gpen") from exc

    device = torch.device(ctx.device)
    model_path = weights_dir / model_filename
    if not model_path.is_file():
        raise NodeExecutionError("gpen", f"weights not found: {model_path.name}")

    state = torch.load(model_path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "params_ema" in state:
        state = state["params_ema"]
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]

    generator = FullGenerator(
        FACE_SIZE, 512, 8, channel_multiplier=2, narrow=1, device=str(device)
    )
    generator.load_state_dict(state, strict=False)
    generator.to(device)
    generator.eval()

    detector_path = weights_dir / YUNET_FILENAME
    rgb, alpha = split_alpha(image)
    faces = detect_faces(
        rgb,
        str(detector_path),
        threshold=float(params.get("detection_threshold", 0.6)),
    )
    faces = select_faces(
        faces,
        rgb.shape[:2],
        only_center=bool(params.get("only_center_face", False)),
        max_faces=int(params.get("max_faces", 0)),
        min_size=int(params.get("min_face_size", 32)),
    )
    if not faces:
        return image

    strength = float(params.get("strength", 1.0))
    out = rgb.copy()
    for face in faces:
        crop, matrix = align_face(rgb, face)
        tensor = to_tensor(crop, device)
        tensor = (tensor - 0.5) / 0.5
        with torch.inference_mode():
            restored, _ = generator(tensor)
        restored = restored * 0.5 + 0.5
        restored_np = to_numpy(restored)
        if strength < 1.0:
            restored_np = crop * (1.0 - strength) + restored_np * strength
        out = paste_face(out, restored_np, matrix)

    return merge_alpha(out, alpha)
