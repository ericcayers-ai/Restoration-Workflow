"""Sixteen built-in workflow presets (ROADMAP.md Phase 4.5.3).

Eight base presets use the permissive stack; eight "full-stack" variants swap in
higher-quality models (CodeFormer, SwinIR-L, defect removal) when installed.
Each preset is a validated ``PipelineJson`` seeded into the preset store on first
run.
"""

from __future__ import annotations

from typing import Any

from .core.ordering import auto_order_pipeline
from .core.registry import NodeRegistry
from .presets import Preset, PresetStore

_BUILTIN: list[tuple[str, str, list[str], dict[str, dict[str, Any]]]] = [
    # Base tier (permissive stack)
    (
        "Animation Cartoon",
        "Flat colours and line art — light denoise, modest upscale, fast face pass.",
        ["fbcnn", "scunet", "realesrgan", "gfpgan"],
        {"realesrgan": {"scale": 2}, "fbcnn": {"quality_factor": 75}},
    ),
    (
        "VHS Capture",
        "VHS tape capture — heavy deblock, blind denoise, 2x upscale.",
        ["fbcnn", "scunet", "realesrgan", "gfpgan"],
        {"fbcnn": {"quality_factor": 50}, "realesrgan": {"scale": 2}},
    ),
    (
        "35mm Film Scan",
        "Scanned film negative — exposure, denoise, quality upscale, face restore.",
        ["exposure_correct", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Digital Photo",
        "Modern digital photo — minimal chain, quality upscale when needed.",
        ["scunet", "realesrgan", "gfpgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Old Film",
        "Pre-video-era motion picture — deblock, denoise, 2x, dual face pass.",
        ["fbcnn", "scunet", "realesrgan", "gfpgan", "restoreformer"],
        {"fbcnn": {"quality_factor": 60}, "realesrgan": {"scale": 2}},
    ),
    (
        "B and W Film",
        "Monochrome film scan — exposure recovery, denoise, upscale.",
        ["exposure_correct", "scunet", "swinir", "gfpgan"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Damaged Print",
        "Scratches and dust — defect mask auto-routes to LaMa.",
        [
            "exposure_correct", "fbcnn", "scunet", "mask_from_image",
            "lama", "realesrgan", "gfpgan",
        ],
        {"mask_from_image": {"source": "defect"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Robust All-in-One",
        "Maximum permissive coverage for unknown degradation.",
        ["exposure_correct", "fbcnn", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 4}},
    ),
    # Full-stack tier (quality models — may need extra downloads / acknowledgement)
    (
        "Animation Cartoon Full",
        "Full-stack animation: SwinIR upscale, RestoreFormer faces.",
        ["fbcnn", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}, "fbcnn": {"quality_factor": 75}},
    ),
    (
        "VHS Capture Full",
        "Full-stack VHS: SwinIR 2x, dual face restoration.",
        ["fbcnn", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"fbcnn": {"quality_factor": 50}, "swinir": {"scale": 2}},
    ),
    (
        "35mm Film Scan Full",
        "Full-stack film scan with HAT upscale when installed.",
        ["exposure_correct", "scunet", "hat", "gfpgan", "restoreformer"],
        {"hat": {"scale": 4}},
    ),
    (
        "Digital Photo Full",
        "Full-stack digital: SwinIR + RestoreFormer.",
        ["scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Old Film Full",
        "Full-stack old film with defect removal.",
        [
            "exposure_correct", "fbcnn", "scunet", "mask_from_image", "lama",
            "swinir", "gfpgan", "restoreformer",
        ],
        {"mask_from_image": {"source": "defect"}, "swinir": {"scale": 2}},
    ),
    (
        "B and W Film Full",
        "Full-stack monochrome with SwinIR upscale.",
        ["exposure_correct", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Damaged Print Full",
        "Full-stack damaged print — always defect mask + LaMa + quality upscale.",
        [
            "exposure_correct", "fbcnn", "scunet", "mask_from_image", "lama",
            "swinir", "gfpgan", "restoreformer",
        ],
        {"mask_from_image": {"source": "defect"}, "swinir": {"scale": 2}},
    ),
    (
        "Robust All-in-One Full",
        "Full permissive + quality stack including CodeFormer opt-in slot.",
        [
            "exposure_correct", "fbcnn", "scunet", "swinir",
            "gfpgan", "restoreformer", "codeformer",
        ],
        {"swinir": {"scale": 4}},
    ),
]


def seed_builtin_presets(store: PresetStore, registry: NodeRegistry) -> int:
    """Write built-in presets that are not already present. Returns count seeded."""
    existing = {p.name for p in store.list()}
    seeded = 0
    for name, description, chain, params in _BUILTIN:
        if name in existing:
            continue
        try:
            spec = auto_order_pipeline(chain, registry, params)
        except Exception:
            continue
        store.save(Preset(name=name, description=description, pipeline=spec.to_dict()))
        seeded += 1
    return seeded


def builtin_preset_names() -> list[str]:
    return [name for name, _, _, _ in _BUILTIN]
