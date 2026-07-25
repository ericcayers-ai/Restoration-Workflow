"""Built-in workflow presets spanning classical / CNN / instruct / diffusion lanes.

Versioned force-refresh: when ``BUILTIN_PRESET_VERSION`` rises, existing builtin
names are rewritten from the catalog so users get the new lanes without a manual
reset. User-authored presets whose names do not appear in the catalog are left alone.

Presets target the active (non-Legacy) stack. DiffBIR and HAT are gone; former
defaults (SCUNet, SwinIR, GFPGAN, …) live under Settings → Legacy only.
"""

from __future__ import annotations

from typing import Any

from .core.ordering import auto_order_pipeline
from .core.registry import NodeRegistry
from .presets import Preset, PresetStore

# Bump when the catalog below changes shape — seed overwrites matching names.
BUILTIN_PRESET_VERSION = 3

# (name, description, chain, params)
_BUILTIN: list[tuple[str, str, list[str], dict[str, dict[str, Any]]]] = [
    # --- Classical / everyday ---
    (
        "Digital Photo",
        "Modern digital photo — light deblock and fast upscale.",
        ["fbcnn", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Phone Snapshot",
        "Phone JPEG — deblock and modest upscale.",
        ["fbcnn", "realesrgan"],
        {"fbcnn": {"quality_factor": 70}, "realesrgan": {"scale": 2}},
    ),
    (
        "Fidelity First",
        "Conservative cleanup — prefer fidelity over punch.",
        ["fbcnn", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Archival Soft",
        "Gentle archival pass — exposure, deblock, modest upscale.",
        ["exposure_correct", "fbcnn", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Damaged Print",
        "Scratches and dust via LaMa (paint a mask in Mask Editor for best results).",
        ["exposure_correct", "fbcnn", "lama", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Low Light Rescue",
        "Classical shadow recovery before upscale.",
        ["exposure_correct", "realesrgan"],
        {"exposure_correct": {"clip_limit": 3.0}, "realesrgan": {"scale": 2}},
    ),
    (
        "Blown Highlight Rescue",
        "Clip-aware exposure + InstructIR highlight regen finish.",
        ["exposure_correct", "instructir"],
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
        "VHS tape capture — heavy deblock and 2x upscale.",
        ["fbcnn", "realesrgan"],
        {"fbcnn": {"quality_factor": 50}, "realesrgan": {"scale": 2}},
    ),
    (
        "35mm Film Scan",
        "Scanned film — exposure, quality upscale, optional OSDFace when acknowledged.",
        ["exposure_correct", "mambair", "osdface"],
        {},
    ),
    (
        "Old Film",
        "Aged motion-picture still — deblock, upscale, face restore.",
        ["fbcnn", "realesrgan", "osdface"],
        {"fbcnn": {"quality_factor": 60}, "realesrgan": {"scale": 2}},
    ),
    (
        "B and W Film",
        "Monochrome restore — no colour invent; exposure + upscale.",
        ["exposure_correct", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Animation Cartoon",
        "Flat colours and line art — light deblock, modest upscale.",
        ["fbcnn", "realesrgan"],
        {"realesrgan": {"scale": 2}, "fbcnn": {"quality_factor": 75}},
    ),
    (
        "Wedding Candid",
        "Candid portrait — quality upscale and OSDFace.",
        ["mambair", "osdface"],
        {},
    ),
    (
        "Portrait OSDFace",
        "Face-first restore with the active OSDFace rail (licence-gated).",
        ["realesrgan", "osdface"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "Robust All-in-One",
        "Maximum active-stack coverage for unknown degradation.",
        ["exposure_correct", "fbcnn", "mambair", "osdface"],
        {},
    ),
    (
        "Colorize BW",
        "DDColor modelscope colourize + light cleanup.",
        ["ddcolor", "realesrgan"],
        {"ddcolor": {"variant": "modelscope"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Colorize Artistic",
        "DDColor artistic variant for punchier colourize.",
        ["ddcolor", "realesrgan"],
        {"ddcolor": {"variant": "artistic"}, "realesrgan": {"scale": 2}},
    ),
    (
        "Night DarkIR",
        "Low-light path preferring DarkIR when installed.",
        ["darkir", "realesrgan"],
        {"realesrgan": {"scale": 2}},
    ),
    (
        "MambaIR Quality",
        "Efficient transformer-class upscale (stretch-tier peer).",
        ["mambair"],
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
        ["fbcnn", "realesrgan", "osdface", "instructir"],
        {
            "instructir": {
                "prompt_preset": "instruct_only_general",
                "mode": "finish_only",
            }
        },
    ),
    # --- Diffusion / generative peers ---
    (
        "SUPIR Maximum",
        "Flagship generative upscale (non-commercial; acknowledge licence).",
        ["realesrgan", "supir"],
        {"supir": {"strength": 0.3}},
    ),
    (
        "InstantIR Creative",
        "Blind restoration with mild creative clarity.",
        ["realesrgan", "instantir"],
        {},
    ),
    (
        "PowerPaint Cleanup",
        "Text-guided inpaint / object removal (wire a mask edge).",
        ["powerpaint"],
        {},
    ),
    (
        "FLUX Fill Guided",
        "FLUX.1-Fill text-guided inpaint (non-commercial; masking category).",
        ["flux_fill"],
        {},
    ),
    (
        "RMBG Matte",
        "Background removal with RMBG-2.0 (non-commercial; acknowledge licence).",
        ["rmbg2"],
        {},
    ),
    # --- Full-stack quality variants ---
    (
        "VHS Capture Full",
        "Full-stack VHS: MambaIR upscale + OSDFace.",
        ["fbcnn", "mambair", "osdface"],
        {"fbcnn": {"quality_factor": 50}},
    ),
    (
        "35mm Film Scan Full",
        "Full-stack film scan with MambaIR upscale.",
        ["exposure_correct", "mambair", "osdface"],
        {},
    ),
    (
        "Old Film Full",
        "Full-stack old film with LaMa defect fill.",
        ["exposure_correct", "fbcnn", "lama", "mambair", "osdface"],
        {"fbcnn": {"quality_factor": 60}},
    ),
    (
        "B and W Film Full",
        "Full-stack monochrome with MambaIR upscale.",
        ["exposure_correct", "mambair"],
        {},
    ),
    (
        "Animation Cartoon Full",
        "Full-stack animation: MambaIR upscale.",
        ["fbcnn", "mambair"],
        {"fbcnn": {"quality_factor": 75}},
    ),
    (
        "Damaged Print Full",
        "Full-stack damaged print — LaMa + quality upscale + face.",
        ["exposure_correct", "fbcnn", "lama", "mambair", "osdface"],
        {},
    ),
    (
        "Robust All-in-One Full",
        "Full active stack including InstructIR finish.",
        ["exposure_correct", "fbcnn", "mambair", "osdface", "instructir"],
        {
            "instructir": {
                "prompt_preset": "instruct_only_general",
                "mode": "finish_only",
            }
        },
    ),
    (
        "Digital Photo Full",
        "Full-stack digital: MambaIR + OSDFace.",
        ["fbcnn", "mambair", "osdface"],
        {},
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
