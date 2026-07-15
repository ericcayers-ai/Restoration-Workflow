"""InstructIR inference runtime (MIT weights from marcosv/InstructIR on HF)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ...core.errors import InferenceUnavailableError, NodeExecutionError
from ...core.types import ImageArray, RunContext
from .._torch import read_state_dict, require_torch


def _mean_pool(model_output: Any, attention_mask: Any) -> Any:
    token_embeddings = model_output[0]
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return (token_embeddings * mask).sum(1) / mask.sum(1).clamp(min=1e-9)


def _encode_instruction(
    instruction: str,
    device: str,
    *,
    text_encoder_dir: Path,
    cache: dict[str, Any],
) -> Any:
    """Frozen BGE-micro encoder → 384-d sentence embedding (local weights only)."""
    import torch  # noqa: PLC0415

    try:
        from transformers import AutoModel, AutoTokenizer  # noqa: PLC0415
    except ImportError as exc:
        raise InferenceUnavailableError("instructir") from exc

    if not text_encoder_dir.is_dir():
        raise NodeExecutionError(
            "instructir",
            f"text encoder weights missing at {text_encoder_dir} "
            "(download InstructIR weights; includes bge-micro-v2)",
        )

    cache_key = f"lm:{text_encoder_dir.resolve()}"
    if cache_key not in cache:
        tokenizer = AutoTokenizer.from_pretrained(str(text_encoder_dir), local_files_only=True)
        model = AutoModel.from_pretrained(str(text_encoder_dir), local_files_only=True)
        model.eval()
        for p in model.parameters():
            p.requires_grad = False
        cache[cache_key] = (tokenizer, model)

    tokenizer, model = cache[cache_key]
    model = model.to(device)
    inputs = tokenizer([instruction], padding=True, truncation=True, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)
        emb = _mean_pool(outputs, inputs["attention_mask"])
        emb = torch.nn.functional.normalize(emb, p=2, dim=1)
    return emb


def _load_models(
    *,
    weights_dir: Path,
    device: str,
    image_weight: str,
    lm_weight: str,
    cache: dict[str, Any],
) -> tuple[Any, Any]:
    torch, _ = require_torch("instructir")
    from ..vendored.instructir_arch import LMHead, create_instructir  # noqa: PLC0415

    img_path = Path(weights_dir) / image_weight
    lm_path = Path(weights_dir) / lm_weight
    cache_key = f"ir:{img_path.resolve()}:{device}"
    if cache_key in cache:
        return cache[cache_key]

    if not img_path.is_file() or not lm_path.is_file():
        raise NodeExecutionError(
            "instructir",
            f"missing weights (need {image_weight} and {lm_weight} in {weights_dir})",
        )

    model = create_instructir()
    state = read_state_dict("instructir", img_path)
    model.load_state_dict(state, strict=True)
    model = model.to(device).eval()

    lm_head = LMHead(embedding_dim=384, hidden_dim=256, num_classes=7)
    lm_state = read_state_dict("instructir", lm_path)
    lm_head.load_state_dict(lm_state, strict=True)
    lm_head = lm_head.to(device).eval()

    cache[cache_key] = (model, lm_head)
    return model, lm_head


def run_instructir(
    image: ImageArray,
    params: dict[str, Any],
    ctx: RunContext,
    *,
    weights_dir: Path,
    image_weight: str = "im_instructir-7d.pt",
    lm_weight: str = "lm_instructir-7d.pt",
    cache: dict[str, Any] | None = None,
    text_encoder_dir: Path | None = None,
) -> ImageArray:
    torch, _ = require_torch("instructir")
    runtime_cache = cache if cache is not None else {}
    encoder_dir = text_encoder_dir or (Path(weights_dir) / "bge-micro-v2")

    instruction = str(params.get("instruction") or "").strip()
    if not instruction:
        instruction = "Restore this photograph: reduce noise, blur, and compression artifacts."

    device = ctx.device if ctx.device else "cpu"
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"

    ctx.check_cancelled()
    ctx.report_progress(0.05, "loading InstructIR")
    model, lm_head = _load_models(
        weights_dir=weights_dir,
        device=device,
        image_weight=image_weight,
        lm_weight=lm_weight,
        cache=runtime_cache,
    )

    rgb = image[..., :3] if image.ndim == 3 and image.shape[2] >= 3 else image
    rgb = np.clip(rgb.astype(np.float32), 0.0, 1.0)
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(device)

    ctx.check_cancelled()
    ctx.report_progress(0.2, "encoding instruction")
    with torch.no_grad():
        raw_emb = _encode_instruction(
            instruction,
            device,
            text_encoder_dir=encoder_dir,
            cache=runtime_cache,
        )
        ctx.check_cancelled()
        ctx.report_progress(0.45, "restoring")
        text_embd, _deg = lm_head(raw_emb)
        out = model(tensor, text_embd)
    ctx.report_progress(0.9, "finalizing")

    restored = out.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy().astype(np.float32)
    strength = float(np.clip(params.get("strength", 1.0), 0.0, 1.0))
    if strength < 1.0:
        restored = rgb * (1.0 - strength) + restored * strength

    if image.ndim == 3 and image.shape[2] == 4:
        restored = np.concatenate([restored, image[..., 3:4]], axis=2).astype(np.float32)
    ctx.report_progress(1.0)
    return restored
