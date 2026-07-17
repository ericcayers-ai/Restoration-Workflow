"""One-shot harvest Scan_12 QA (heuristic VLM + scratch mask). Not part of pytest."""

from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from restoration.core.images import load_image_bytes
from restoration.core.quality import QualityTier
from restoration.nodes.masks import defect_mask_rgb
from restoration.service import AppServices

ROOT = Path(__file__).resolve().parents[3]
SRC = Path(__file__).with_name("Scan_12_harvest_source.png")
OUT = Path(__file__).parent


def main() -> None:
    raw = SRC.read_bytes()
    img = load_image_bytes(raw)
    h, w = img.shape[:2]
    pil = Image.open(BytesIO(raw))
    report: dict = {
        "source": str(SRC.relative_to(ROOT)),
        "image_size": {"width": w, "height": h},
        "exif_dpi": pil.info.get("dpi"),
        "print_dpi_advice": {
            f"{inches}in_at_300dpi_needs_px": inches * 300 for inches in (4, 5, 6, 8)
        },
        "print_note": (
            f"Scan is {w}×{h}px. At 300 DPI that prints ~{w / 300:.1f}×{h / 300:.1f} in; "
            "downscale only if the target print is smaller than that native size."
        ),
    }

    with tempfile.TemporaryDirectory() as tmp:
        svc = AppServices(data_dir=Path(tmp), force_cpu=True, seed_builtin_presets=True)
        report["vlm_status"] = svc.vlm.status()

        desc = svc.describe_photo(img, force_heuristic=True)
        report["describe_heuristic"] = desc.to_dict()

        plan = svc.plan_auto(
            img,
            goal="archival B&W restore for print",
            quality_tier=QualityTier.BALANCED,
            fallback="skill",
            force_heuristic=True,
        )
        report["plan_archival"] = {
            "pipeline_nodes": [
                n.get("type") for n in (plan.get("pipeline") or {}).get("nodes", [])
            ],
            "reasons": (plan.get("routing") or {}).get("reasons") or plan.get("reasons"),
            "keys": sorted(plan.keys()),
        }

        plan_color = svc.plan_auto(
            img,
            goal="colorize",
            quality_tier=QualityTier.BALANCED,
            fallback="skill",
            force_heuristic=True,
        )
        report["plan_colorize"] = {
            "pipeline_nodes": [
                n.get("type") for n in (plan_color.get("pipeline") or {}).get("nodes", [])
            ],
        }

        suggest = svc.suggest_auto_presets(
            img, goal="restore harvest scan", force_heuristic=True
        )
        report["suggest"] = {
            "names": [s.get("name") for s in suggest.get("suggestions", [])],
            "vlm": suggest.get("vlm"),
        }

        auto = svc.analyze(img, QualityTier.BALANCED)
        report["analyze"] = {
            "profile": auto.profile.to_dict(),
            "pipeline_nodes": [n.type for n in auto.spec.nodes],
            "reasons": auto.decision.reasons,
        }

    mask = defect_mask_rgb(img[..., :3])
    report["scratch_mask_mean"] = float(mask.mean())
    Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), mode="L").save(
        OUT / "Scan_12_scratch_mask.png"
    )
    rgb = (np.clip(img[..., :3], 0, 1) * 255).astype(np.uint8)
    overlay = rgb.copy()
    hit = mask > 0.3
    overlay[hit] = (0.55 * overlay[hit] + 0.45 * np.array([232, 135, 58])).astype(np.uint8)
    Image.fromarray(overlay).save(OUT / "Scan_12_scratch_overlay.png")
    report["artifacts"] = [
        "Scan_12_harvest_source.png",
        "Scan_12_scratch_mask.png",
        "Scan_12_scratch_overlay.png",
    ]
    report["gaps"] = [
        "Full GPU E2E (denoise/OSDFace/inpaint weights) not run — CPU heuristic path only.",
        "Qwen2.5-VL weights not installed — describe/plan used force_heuristic=True.",
        "No true before/after restore pixels from LaMa/RealESRGAN (weights may be missing).",
    ]

    out_json = OUT / "Scan_12_harvest_qa.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2)[:7000])
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
