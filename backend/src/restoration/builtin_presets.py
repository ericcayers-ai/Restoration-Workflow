"""Built-in workflow presets spanning classical / CNN / instruct / diffusion lanes.

Versioned force-refresh: when ``BUILTIN_PRESET_VERSION`` rises, existing builtin
names are rewritten from the catalog so users get the new lanes without a manual
reset. User-authored presets whose names do not appear in the catalog are left alone.
"""

from __future__ import annotations

from typing import Any

from .core.ordering import auto_order_pipeline
from .core.registry import NodeRegistry
from .presets import Preset, PresetStore

# Bump when the catalog below changes shape — seed overwrites matching names.
BUILTIN_PRESET_VERSION = 2

# (name, description, chain, params)
_BUILTIN: list[tuple[str, str, list[str], dict[str, dict[str, Any]]]] = [
    # --- Classical / everyday ---
    (
        "Digital Photo",
        "Modern digital photo — light denoise and fast upscale.",
        ["scunet", "realesrgan", "gfpgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Phone Snapshot",
        "Phone JPEG — deblock, denoise, modest upscale.",
        ["fbcnn", "scunet", "realesrgan"],
        {"fbcnn": {"quality_factor": 70}, "realesrgan": {"scale": 2}},
    ),
    (
        "Fidelity First",
        "Conservative cleanup — prefer fidelity over punch.",
        ["fbcnn", "scunet", "realesrgan"],
        {"scunet": {"variant": "psnr"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Archival Soft",
        "Gentle archival pass — defects + soft face restore.",
        ["exposure_correct", "fbcnn", "scunet", "old_photos_scratch", "gfpgan"],
        {},
    ),
    (
        "Damaged Print",
        "Scratches and dust via defect mask + LaMa.",
        [
            "exposure_correct", "fbcnn", "scunet", "mask_from_image",
            "lama", "realesrgan", "gfpgan",
        ],
        {"mask_from_image": {"source": "defect"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Low Light Rescue",
        "Classical shadow recovery before denoise/upscale.",
        ["exposure_correct", "scunet", "realesrgan"],
        {"exposure_correct": {"clip_limit": 3.0}, "realesrgan": {"scale": 2}},
    ),
    (
        "Blown Highlight Rescue",
        "Clip-aware exposure + InstructIR highlight regen finish.",
        ["exposure_correct", "scunet", "instructir"],
        {
            "exposure_correct": {"clip_limit": 2.0, "strength": 0.85},
            "instructir": {
                "prompt_preset": "blown_highlight_rescue",
                "mode": "finish_only",
                "mask_highlights": True,
                "instruction": (
                    "Regenerate natural detail in overexposed and blown-out regions; "
                    "preserve unclipped areas."
                ),
            },
        },
    ),
    # --- CNN / film ---
    (
        "VHS Capture",
        "VHS tape capture — heavy deblock, blind denoise, 2x upscale.",
        ["fbcnn", "scunet", "realesrgan", "gfpgan"],
        {"fbcnn": {"quality_factor": 50}, "realesrgan": {"scale": 2}},
    ),
    (
        "35mm Film Scan",
        "Scanned film — exposure, denoise, quality upscale, faces.",
        ["exposure_correct", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Old Film",
        "Aged motion-picture still — deblock, denoise, dual face.",
        ["fbcnn", "scunet", "realesrgan", "gfpgan", "restoreformer"],
        {"fbcnn": {"quality_factor": 60}, "realesrgan": {"scale": 2}},
    ),
    (
        "B and W Film",
        "Monochrome restore — no colour invent; exposure + denoise + upscale.",
        ["exposure_correct", "scunet", "swinir", "gfpgan"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Animation Cartoon",
        "Flat colours and line art — light denoise, modest upscale.",
        ["fbcnn", "scunet", "realesrgan", "gfpgan"],
        {"realesrgan": {"scale": 2}, "fbcnn": {"quality_factor": 75}},
    ),
    (
        "Wedding Candid",
        "Candid portrait — denoise, quality upscale, dual face.",
        ["scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}},
    ),
    (
        "Dual Face Natural",
        "Fast + quality face cascade for soft portraits.",
        ["scunet", "realesrgan", "gfpgan", "restoreformer"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Robust All-in-One",
        "Maximum permissive coverage for unknown degradation.",
        ["exposure_correct", "fbcnn", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 4}},
    ),
    (
        "Colorize BW",
        "DDColor modelscope colourize + light cleanup.",
        ["ddcolor", "scunet", "realesrgan"],
        {"ddcolor": {"variant": "modelscope"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Colorize Artistic",
        "DDColor artistic variant for punchier colourize.",
        ["ddcolor", "scunet", "realesrgan"],
        {"ddcolor": {"variant": "artistic"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Night DarkIR",
        "Low-light path preferring DarkIR when installed.",
        ["darkir", "scunet", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "MambaIR Quality",
        "Efficient transformer-class upscale (stretch-tier peer).",
        ["scunet", "mambair"],
        {},
    ),
    # --- Instruct lane ---
    (
        "InstructIR Solo",
        "Master Restorer alone — one instruction, all-in-one cleanup.",
        ["instructir"],
        {
            "instructir": {
                "prompt_preset": "instruct_only_general",
                "mode": "instruct_only",
            }
        },
    ),
    (
        "Master Guided Ensemble",
        "Specialists + InstructIR finish (guide_and_finish starting point).",
        ["fbcnn", "scunet", "realesrgan", "gfpgan", "instructir"],
        {
            "instructir": {
                "prompt_preset": "instruct_only_general",
                "mode": "finish_only",
            }
        },
    ),
    # --- Diffusion / generative peers ---
    (
        "DiffBIR Polish",
        "Diffusion blind restore polish after classical denoise.",
        ["scunet", "diffbir"],
        {"diffbir": {"strength": 0.35, "prompt": "high quality photograph, sharp, detailed"}},
    ),
    (
        "SUPIR Maximum",
        "Flagship generative upscale (non-commercial; acknowledge licence).",
        ["scunet", "supir"],
        {"supir": {"strength": 0.3}},
    ),
    (
        "InstantIR Creative",
        "Blind restoration with mild creative clarity.",
        ["scunet", "instantir"],
        {},
    ),
    (
        "PowerPaint Cleanup",
        "Text-guided inpaint / object removal.",
        ["mask_from_image", "powerpaint"],
        {"mask_from_image": {"source": "defect"}},
    ),
    (
        "FLUX Fill Guided",
        "FLUX.1-Fill text-guided inpaint (non-commercial).",
        ["mask_from_image", "flux_fill"],
        {"mask_from_image": {"source": "defect"}},
    ),
    # --- Full-stack quality variants ---
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
        "Animation Cartoon Full",
        "Full-stack animation: SwinIR upscale, RestoreFormer faces.",
        ["fbcnn", "scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}, "fbcnn": {"quality_factor": 75}},
    ),
    (
        "Damaged Print Full",
        "Full-stack damaged print — defect mask + LaMa + quality upscale.",
        [
            "exposure_correct", "fbcnn", "scunet", "mask_from_image", "lama",
            "swinir", "gfpgan", "restoreformer",
        ],
        {"mask_from_image": {"source": "defect"}, "swinir": {"scale": 2}},
    ),
    (
        "Robust All-in-One Full",
        "Full permissive + quality stack including CodeFormer opt-in.",
        [
            "exposure_correct", "fbcnn", "scunet", "swinir",
            "gfpgan", "restoreformer", "codeformer",
        ],
        {"swinir": {"scale": 4}},
    ),
    (
        "Digital Photo Full",
        "Full-stack digital: SwinIR + RestoreFormer.",
        ["scunet", "swinir", "gfpgan", "restoreformer"],
        {"swinir": {"scale": 2}},
    ),
]


def builtin_preset_names() -> list[str]:
    return [name for name, _, _, _ in _BUILTIN]


def seed_builtin_presets(
    store: PresetStore,
    registry: NodeRegistry,
    *,
    force_version: int | None = None,
) -> int:
    """Write / refresh built-in presets. Returns count written.

    When ``force_version`` (default: ``BUILTIN_PRESET_VERSION``) is greater than
    the marker file on disk, all catalog names are overwritten.
    """
    target = force_version if force_version is not None else BUILTIN_PRESET_VERSION
    marker = store.root / ".builtin_version"
    current = 0
    if marker.is_file():
        try:
            current = int(marker.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            current = 0
    refresh = target > current

    existing = {p.name for p in store.list()}
    written = 0
    for name, description, chain, params in _BUILTIN:
        if name in existing and not refresh:
            continue
        try:
            spec = auto_order_pipeline(chain, registry, params)
        except Exception:
            continue
        store.save(Preset(name=name, description=description, pipeline=spec.to_dict()))
        written += 1

    store.root.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(target), encoding="utf-8")
    return written
