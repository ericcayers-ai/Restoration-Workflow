"""Local Qwen2.5-VL vision model for photo description (Phase 4 Auto).

Weights live under ``<data>/weights/vlm/qwen2.5-vl-7b-instruct/`` and download
on demand — same explicit-download rule as node weights. When the model is
missing or transformers is not installed, ``describe_photo`` falls back to a
structured heuristic built from ``DegradationAnalyzer``.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .analyzer import DegradationAnalyzer, DegradationProfile
from .errors import InsufficientDiskSpaceError, JobCancelled, WeightsNotInstalledError
from .types import ImageArray

VLM_REPO_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
VLM_DIR_NAME = "qwen2.5-vl-7b-instruct"
VLM_SIZE_BYTES = 15_500_000_000
VLM_LICENSE_SPDX = "Apache-2.0"

_DESCRIBE_PROMPT = """You are a photo-restoration analyst. Describe this image for a local
restoration pipeline. Reply with ONLY valid JSON matching this schema:
{
  "content_type": "portrait|group|landscape|document|object|mixed|unknown",
  "is_grayscale": bool,
  "is_bw_intended": bool,
  "has_faces": bool,
  "face_count": int,
  "degradations": ["jpeg"|"blur"|"noise"|"grain"|"scratches"|"low_light"|"blown_highlights"|"fade"|"stain"],
  "severity": {"jpeg":0-1, "blur":0-1, "noise":0-1, "scratches":0-1, "exposure":0-1},
  "highlights_blown": bool,
  "scratches_likely": bool,
  "grain_or_noise": bool,
  "recommended_print_dpi": 150|300|600|null,
  "downscale_advice": string|null,
  "summary": "one short sentence"
}
Be conservative: only flag degradations you can see. Prefer archival B&W
(is_bw_intended=true) for intentionally monochrome photos, not faded colour.
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass
class PhotoDescription:
    content_type: str = "unknown"
    is_grayscale: bool = False
    is_bw_intended: bool = False
    has_faces: bool = False
    face_count: int = 0
    degradations: list[str] = field(default_factory=list)
    severity: dict[str, float] = field(default_factory=dict)
    highlights_blown: bool = False
    scratches_likely: bool = False
    grain_or_noise: bool = False
    width: int = 0
    height: int = 0
    recommended_print_dpi: int | None = None
    downscale_advice: str | None = None
    summary: str = ""
    source: str = "heuristic"  # "vlm" | "heuristic"
    confidence: float = 0.5
    profile: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def defect_score(self) -> float:
        try:
            return float((self.profile or {}).get("defect_score") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhotoDescription:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def _print_dpi_advice(width: int, height: int) -> tuple[int | None, str | None]:
    long_edge = max(width, height)
    if long_edge <= 0:
        return None, None
    if long_edge < 1200:
        return 150, (
            f"Long edge is {long_edge}px — upscale before a large print; "
            "target ~300 DPI at final print size."
        )
    if long_edge < 2500:
        return 300, (
            f"Long edge is {long_edge}px — suitable for ~6–8\" prints at 300 DPI; "
            "upscale if printing larger."
        )
    if long_edge > 6000:
        return 300, (
            f"Long edge is {long_edge}px — consider mild downscale for screen/web "
            "or keep full res for archival."
        )
    return 300, None


def description_from_profile(profile: DegradationProfile) -> PhotoDescription:
    """CPU fallback: structured description from the degradation analyzer."""
    degradations: list[str] = []
    severity: dict[str, float] = {}

    if profile.jpeg_blockiness >= 0.12:
        degradations.append("jpeg")
        severity["jpeg"] = min(1.0, profile.jpeg_blockiness / 0.5)
    if profile.blur_score < 80:
        degradations.append("blur")
        severity["blur"] = min(1.0, (80 - profile.blur_score) / 80)
    if profile.noise_score >= 0.02:
        degradations.append("noise")
        severity["noise"] = min(1.0, profile.noise_score / 0.08)
        if profile.noise_score >= 0.04:
            degradations.append("grain")
    if profile.low_light or profile.under_exposure >= 0.35:
        degradations.append("low_light")
        severity["exposure"] = max(severity.get("exposure", 0.0), profile.under_exposure)
    if profile.blown_highlights or profile.clip_fraction >= 0.02:
        degradations.append("blown_highlights")
        severity["exposure"] = max(severity.get("exposure", 0.0), profile.over_exposure)
    if profile.defect_score >= 0.015:
        degradations.append("scratches")
        severity["scratches"] = min(1.0, profile.defect_score / 0.05)

    faces = int(profile.face_count or 0)
    dpi, advice = _print_dpi_advice(profile.width, profile.height)
    content = "unknown"
    if faces >= 3:
        content = "group"
    elif faces >= 1:
        content = "portrait"

    summary_parts = []
    if profile.is_grayscale:
        summary_parts.append("grayscale")
    if degradations:
        summary_parts.append(", ".join(degradations[:4]))
    if faces:
        summary_parts.append(f"{faces} face(s)")
    summary = "; ".join(summary_parts) or "clean photo — light restore"

    return PhotoDescription(
        content_type=content,
        is_grayscale=profile.is_grayscale,
        is_bw_intended=profile.is_grayscale and profile.mean_saturation < 0.08,
        has_faces=faces >= 1,
        face_count=faces,
        degradations=degradations,
        severity=severity,
        highlights_blown=bool(profile.blown_highlights or profile.clip_fraction >= 0.02),
        scratches_likely=profile.defect_score >= 0.015,
        grain_or_noise=profile.noise_score >= 0.02,
        width=profile.width,
        height=profile.height,
        recommended_print_dpi=dpi,
        downscale_advice=advice,
        summary=summary,
        source="heuristic",
        confidence=0.55,
        profile=profile.to_dict(),
    )


def _parse_vlm_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in VLM response")
    return json.loads(text[start : end + 1])


def _merge_vlm_payload(
    raw: dict[str, Any], profile: DegradationProfile
) -> PhotoDescription:
    base = description_from_profile(profile)
    degradations = list(raw.get("degradations") or base.degradations)
    severity = dict(base.severity)
    for key, val in (raw.get("severity") or {}).items():
        try:
            severity[str(key)] = float(val)
        except (TypeError, ValueError):
            continue
    dpi = raw.get("recommended_print_dpi", base.recommended_print_dpi)
    try:
        dpi_i = int(dpi) if dpi is not None else None
    except (TypeError, ValueError):
        dpi_i = base.recommended_print_dpi
    face_count = int(raw.get("face_count", base.face_count) or 0)
    return PhotoDescription(
        content_type=str(raw.get("content_type") or base.content_type),
        is_grayscale=bool(raw.get("is_grayscale", base.is_grayscale)),
        is_bw_intended=bool(raw.get("is_bw_intended", base.is_bw_intended)),
        has_faces=bool(raw.get("has_faces", face_count >= 1)),
        face_count=face_count,
        degradations=degradations,
        severity=severity,
        highlights_blown=bool(raw.get("highlights_blown", base.highlights_blown)),
        scratches_likely=bool(raw.get("scratches_likely", base.scratches_likely)),
        grain_or_noise=bool(raw.get("grain_or_noise", base.grain_or_noise)),
        width=profile.width,
        height=profile.height,
        recommended_print_dpi=dpi_i,
        downscale_advice=(
            str(raw["downscale_advice"])
            if raw.get("downscale_advice")
            else base.downscale_advice
        ),
        summary=str(raw.get("summary") or base.summary),
        source="vlm",
        confidence=0.85,
        profile=profile.to_dict(),
    )


class VlmManager:
    """Owns the VLM cache directory under ``weights/vlm/``."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        free_space_margin: int = 1 * 1024 * 1024 * 1024,
    ) -> None:
        self.root = Path(root) if root else Path("weights") / "vlm"
        self.root.mkdir(parents=True, exist_ok=True)
        self.model_dir = self.root / VLM_DIR_NAME
        self._free_space_margin = free_space_margin
        self._analyzer = DegradationAnalyzer()

    def is_installed(self) -> bool:
        cfg = self.model_dir / "config.json"
        if not cfg.is_file():
            return False
        return any(self.model_dir.glob("*.safetensors")) or any(self.model_dir.glob("*.bin"))

    def status(self) -> dict[str, Any]:
        installed = self.is_installed()
        size_on_disk = 0
        if self.model_dir.is_dir():
            size_on_disk = sum(
                f.stat().st_size for f in self.model_dir.rglob("*") if f.is_file()
            )
        return {
            "id": "vlm",
            "model_id": VLM_REPO_ID,
            "display_name": "Qwen2.5-VL-7B-Instruct",
            "license_spdx": VLM_LICENSE_SPDX,
            "installed": installed,
            "path": str(self.model_dir),
            "size_bytes": VLM_SIZE_BYTES,
            "size_on_disk": size_on_disk,
            "missing_size_bytes": 0 if installed else max(0, VLM_SIZE_BYTES - size_on_disk),
            "inference_available": self._inference_deps_available(),
        }

    @staticmethod
    def _inference_deps_available() -> bool:
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def download(
        self,
        progress: Callable[[str, int, int], None] | None = None,
        *,
        check_cancel: Callable[[], None] | None = None,
    ) -> Path:
        """Download the Hub snapshot into ``model_dir``. Blocking."""
        if self.is_installed():
            return self.model_dir

        free = shutil.disk_usage(self.root).free
        needed = VLM_SIZE_BYTES
        if needed + self._free_space_margin > free:
            raise InsufficientDiskSpaceError(required=needed, free=free)

        self.model_dir.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("snapshot", 0, VLM_SIZE_BYTES)

        try:
            from huggingface_hub import snapshot_download  # noqa: PLC0415
        except ImportError as exc:
            raise WeightsNotInstalledError("vlm") from exc

        class _CancelProbe:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.n = 0
                self.total = kwargs.get("total") or VLM_SIZE_BYTES

            def update(self, n: int = 1) -> None:
                if check_cancel is not None:
                    check_cancel()
                self.n += n
                if progress:
                    progress("snapshot", min(self.n, int(self.total)), int(self.total))

            def close(self) -> None:
                return None

            def __enter__(self) -> _CancelProbe:
                return self

            def __exit__(self, *args: Any) -> None:
                return None

        try:
            if check_cancel is not None:
                check_cancel()
            snapshot_download(
                repo_id=VLM_REPO_ID,
                local_dir=str(self.model_dir),
                local_dir_use_symlinks=False,
                tqdm_class=_CancelProbe,
            )
        except JobCancelled:
            raise

        if progress:
            progress("snapshot", VLM_SIZE_BYTES, VLM_SIZE_BYTES)

        if not self.is_installed():
            raise WeightsNotInstalledError("vlm")
        return self.model_dir

    def remove(self) -> bool:
        if self.model_dir.exists():
            shutil.rmtree(self.model_dir)
            return True
        return False

    def describe_photo(
        self,
        image: ImageArray,
        *,
        profile: DegradationProfile | None = None,
        force_heuristic: bool = False,
    ) -> PhotoDescription:
        """Return a structured restoration description for ``image``."""
        profile = profile or self._analyzer.analyze(image)
        if force_heuristic or not self.is_installed() or not self._inference_deps_available():
            return description_from_profile(profile)

        try:
            raw = self._run_vlm(image)
            return _merge_vlm_payload(raw, profile)
        except Exception:
            desc = description_from_profile(profile)
            desc.summary = f"{desc.summary} (VLM unavailable — heuristic)"
            return desc

    def _run_vlm(self, image: ImageArray) -> dict[str, Any]:
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration  # noqa: PLC0415

        rgb = image[..., :3] if image.ndim == 3 and image.shape[-1] >= 3 else image
        if rgb.dtype != np.uint8:
            arr = np.clip(rgb, 0, 1)
            if arr.max() <= 1.0:
                arr = (arr * 255.0).astype(np.uint8)
            else:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
        else:
            arr = rgb
        if arr.ndim == 2:
            pil = Image.fromarray(arr, mode="L").convert("RGB")
        else:
            pil = Image.fromarray(arr, mode="RGB")

        max_edge = 1024
        w, h = pil.size
        scale = max(w, h) / max_edge
        if scale > 1:
            pil = pil.resize((int(w / scale), int(h / scale)), Image.Resampling.LANCZOS)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            str(self.model_dir),
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else None,
        )
        if device == "cpu":
            model = model.to(device)
        processor = AutoProcessor.from_pretrained(str(self.model_dir))

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": pil},
                    {"type": "text", "text": _DESCRIBE_PROMPT},
                ],
            }
        ]
        try:
            from qwen_vl_utils import process_vision_info  # noqa: PLC0415

            text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
        except ImportError:
            inputs = processor(
                text=[_DESCRIBE_PROMPT],
                images=[pil],
                return_tensors="pt",
                padding=True,
            )

        inputs = {k: v.to(model.device) if hasattr(v, "to") else v for k, v in inputs.items()}
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=512)
        trimmed = generated[:, inputs["input_ids"].shape[1] :]
        text_out = processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        return _parse_vlm_json(text_out)
