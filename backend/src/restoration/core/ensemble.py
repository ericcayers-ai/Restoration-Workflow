"""Instruction-guided ensemble conductor.

Maps a Master Restorer prompt preset (or freeform instruction + ensemble_hint)
plus a DegradationProfile into a specialist pipeline chain, optionally topped
with an InstructIR finish pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .analyzer import DegradationProfile
from .errors import PipelineValidationError
from .instruction import list_prompt_presets, prompt_by_id
from .ordering import auto_order_pipeline
from .registry import NodeRegistry

VALID_ENSEMBLE_MODES = frozenset({"finish_only", "instruct_only", "guide_and_finish"})


@dataclass
class EnsemblePlan:
    chain: list[str]
    params: dict[str, dict[str, Any]]
    append_instructir: bool
    instruction: str
    prompt_preset_id: str | None
    reasons: list[dict[str, str]] = field(default_factory=list)
    specialist_pipeline: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain,
            "params": self.params,
            "append_instructir": self.append_instructir,
            "instruction": self.instruction,
            "prompt_preset_id": self.prompt_preset_id,
            "reasons": self.reasons,
            "pipeline": self.specialist_pipeline,
        }


# Hint → candidate specialist nodes (filtered by profile + availability).
_HINT_STAGES: dict[str, list[str]] = {
    "deblock_denoise": ["fbcnn", "scunet", "realesrgan"],
    "heavy_denoise": ["scunet", "swinir_denoise", "realesrgan"],
    "face_quality": ["scunet", "swinir", "gfpgan", "restoreformer"],
    "low_light": ["exposure_correct", "darkir", "scunet", "realesrgan"],
    "highlight_regen": ["exposure_correct", "instructir", "diffbir", "scunet"],
    "defect_inpaint": [
        "exposure_correct", "fbcnn", "scunet", "mask_from_image", "lama", "realesrgan",
    ],
    "vhs": ["fbcnn", "scunet", "realesrgan", "gfpgan"],
    "film_scan": ["exposure_correct", "scunet", "swinir", "gfpgan", "restoreformer"],
    "bw_no_color": ["exposure_correct", "scunet", "swinir", "gfpgan"],
    "colorize": ["ddcolor", "scunet", "realesrgan"],
    "archival": ["exposure_correct", "fbcnn", "scunet", "old_photos_scratch", "swinir"],
    "generative_polish": ["scunet", "diffbir", "realesrgan"],
    "fidelity": ["fbcnn", "scunet", "realesrgan"],
    "animation": ["fbcnn", "scunet", "realesrgan", "gfpgan"],
    "instruct_only": ["instructir"],
    "inpaint": ["mask_from_image", "powerpaint", "lama"],
    "quality_upscale": ["scunet", "mambair", "swinir"],
}


def _available(node_id: str, registry: NodeRegistry) -> bool:
    try:
        registry.get_class(node_id)
        return True
    except Exception:
        return False


def _weight_ready(
    node_id: str,
    registry: NodeRegistry,
    installed: set[str] | None,
    acknowledged: set[str] | None,
) -> bool:
    if installed is None:
        return True
    if node_id not in installed:
        return False
    try:
        cls = registry.get_class(node_id)
    except Exception:
        return False
    if cls.license.requires_acknowledgement:
        if acknowledged is None:
            return False
        return node_id in acknowledged
    return True


def _infer_hint(instruction: str) -> str:
    text = instruction.lower()
    if any(w in text for w in ("blow", "overexpos", "highlight", "clip")):
        return "highlight_regen"
    if any(w in text for w in ("low-light", "underexpos", "dark", "night", "shadow")):
        return "low_light"
    if any(w in text for w in ("scratch", "dust", "defect", "tear")):
        return "defect_inpaint"
    if any(w in text for w in ("coloriz", "colouriz")):
        return "colorize"
    if "jpeg" in text or "block" in text or "compression" in text:
        return "deblock_denoise"
    if "noise" in text or "grain" in text:
        return "heavy_denoise"
    if "face" in text or "portrait" in text:
        return "face_quality"
    if "vhs" in text:
        return "vhs"
    return "fidelity"


def build_guided_ensemble(
    profile: DegradationProfile | None,
    *,
    registry: NodeRegistry,
    prompt_preset_id: str | None = None,
    instruction: str | None = None,
    mode: str = "guide_and_finish",
    installed: set[str] | None = None,
    acknowledged: set[str] | None = None,
) -> EnsemblePlan:
    """Build a specialist chain from prompt intent + optional analyzer profile."""
    if mode not in VALID_ENSEMBLE_MODES:
        raise PipelineValidationError(
            f"invalid ensemble mode {mode!r}; expected one of "
            f"{sorted(VALID_ENSEMBLE_MODES)}"
        )
    preset = prompt_by_id(prompt_preset_id) if prompt_preset_id else None
    hint = (preset or {}).get("ensemble_hint") or _infer_hint(instruction or "")
    text = instruction or (preset or {}).get("instruction") or ""
    if not text and preset:
        text = str(preset.get("instruction", ""))

    if mode == "instruct_only" or hint == "instruct_only":
        chain = ["instructir"]
        params = {
            "instructir": {
                "prompt_preset": prompt_preset_id or "instruct_only_general",
                "instruction": text,
                "mode": "instruct_only",
            }
        }
        plan = EnsemblePlan(
            chain=chain,
            params=params,
            append_instructir=False,
            instruction=text,
            prompt_preset_id=prompt_preset_id,
            reasons=[{"node": "instructir", "reason": "Master Restorer instruct-only mode"}],
        )
        plan.specialist_pipeline = auto_order_pipeline(chain, registry, params).to_dict()
        return plan

    candidates = list(_HINT_STAGES.get(hint, _HINT_STAGES["fidelity"]))
    reasons: list[dict[str, str]] = []
    chain: list[str] = []
    params: dict[str, dict[str, Any]] = {}

    metrics = profile.metrics() if profile is not None else {}

    def add(node_id: str, reason: str, node_params: dict[str, Any] | None = None) -> None:
        if node_id in chain:
            return
        if not _available(node_id, registry):
            return
        # Prefer ready weights when awareness is provided; still include permissive
        # classical nodes even if not "installed" (no weights).
        cls = registry.get_class(node_id)
        if cls.weight_manifest and installed is not None:
            if not _weight_ready(node_id, registry, installed, acknowledged):
                # Skip gated/unavailable ML companions; keep classical fallbacks.
                if cls.license.requires_acknowledgement or node_id in {
                    "diffbir", "supir", "darkir", "mambair", "powerpaint", "instantir",
                }:
                    return
        chain.append(node_id)
        if node_params:
            params[node_id] = dict(node_params)
        reasons.append({"node": node_id, "reason": reason})

    # Profile-gated enrichments layered on the hint list.
    if profile is not None:
        if metrics.get("low_light") or metrics.get("under_exposure", 0) > 0.45:
            add("exposure_correct", "profile: underexposure")
            if _weight_ready("darkir", registry, installed, acknowledged):
                add("darkir", "profile: DarkIR ready for low-light")
        if metrics.get("blown_highlights") or metrics.get("clip_fraction", 0) > 0.04:
            add("exposure_correct", "profile: blown highlights")
            if hint == "highlight_regen":
                if _weight_ready("instructir", registry, installed, acknowledged):
                    add(
                        "instructir",
                        "profile: InstructIR highlight regen",
                        {
                            "prompt_preset": "blown_highlight_rescue",
                            "instruction": text or (
                                prompt_by_id("blown_highlight_rescue") or {}
                            ).get("instruction", ""),
                            "mode": "finish_only",
                            "mask_highlights": True,
                        },
                    )
                elif _weight_ready("diffbir", registry, installed, acknowledged):
                    add("diffbir", "profile: DiffBIR highlight companion")
        if metrics.get("jpeg_blockiness", 0) >= 0.10:
            add("fbcnn", "profile: JPEG blockiness")
        if metrics.get("noise_score", 0) >= 0.007:
            add("scunet", "profile: noise")
        if metrics.get("is_grayscale") and hint != "bw_no_color":
            add("ddcolor", "profile: grayscale colourize")
        if metrics.get("face_count") and metrics["face_count"] >= 1:
            add("gfpgan", "profile: faces")
        if metrics.get("defect_score", 0) >= 0.01:
            add("mask_from_image", "profile: defects", {"source": "defect", "dilate": 2})
            add("lama", "profile: defect inpaint")

    for node_id in candidates:
        add(node_id, f"ensemble hint '{hint}'")

    append = mode in ("finish_only", "guide_and_finish") and "instructir" not in chain

    if not chain:
        chain = ["scunet", "realesrgan"]
        reasons.append({"node": "scunet", "reason": "fallback specialist chain"})

    if not (append and _available("instructir", registry)):
        append = False

    if append:
        params.setdefault("instructir", {})
        params["instructir"].update({
            "prompt_preset": prompt_preset_id or "instruct_only_general",
            "instruction": text,
            "mode": "finish_only",
        })
        if hint == "highlight_regen" or prompt_preset_id == "blown_highlight_rescue":
            params["instructir"]["mask_highlights"] = True
        full_chain = list(chain) + ["instructir"]
        reasons.append({
            "node": "instructir",
            "reason": f"Master Restorer finish: {text[:80]}",
        })
    else:
        full_chain = list(chain)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for n in full_chain:
        if n not in seen:
            seen.add(n)
            deduped.append(n)

    plan = EnsemblePlan(
        chain=deduped,
        params=params,
        append_instructir=append,
        instruction=text,
        prompt_preset_id=prompt_preset_id,
        reasons=reasons,
    )
    plan.specialist_pipeline = auto_order_pipeline(deduped, registry, params).to_dict()
    return plan


def prompt_library_summary() -> dict[str, Any]:
    presets = list_prompt_presets()
    return {"version": 1, "count": len(presets), "presets": presets}
