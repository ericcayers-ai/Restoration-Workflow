"""Skill-driven Auto planner: PhotoDescription + goal → PipelineJson.

Uses ``skills/restoration-auto/SKILL.md`` as the human-readable contract.
When the VLM is missing, callers may fall back to ``RuleTable`` via
``AppServices.analyze`` — this module builds plans from a structured
description (VLM or heuristic).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ordering import auto_order_pipeline
from .quality import QualityTier, apply_quality_tier
from .registry import NodeRegistry
from .rules import RoutingDecision
from .types import NodeCategory
from .vlm import PhotoDescription


def skill_md_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    repo = here.parents[4]
    return [
        repo / "skills" / "restoration-auto" / "SKILL.md",
        repo / "docs" / "restoration-auto-SKILL.md",
        here.parent / "data" / "restoration-auto-SKILL.md",
    ]


def load_skill_text() -> str:
    for path in skill_md_candidates():
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


def skill_path() -> str | None:
    for path in skill_md_candidates():
        if path.is_file():
            return str(path)
    return None


@dataclass
class SuggestedPreset:
    name: str
    description: str
    pipeline: dict[str, Any]
    reasons: list[dict[str, str]] = field(default_factory=list)
    goal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "pipeline": self.pipeline,
            "reasons": self.reasons,
            "goal": self.goal,
            "suggested": True,
        }


@dataclass
class AutoPlan:
    description: PhotoDescription
    decision: RoutingDecision
    pipeline: dict[str, Any]
    suggestions: list[SuggestedPreset] = field(default_factory=list)
    planner: str = "skill"
    skill_path: str | None = None
    goal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description.to_dict(),
            "profile": self.description.profile,
            "routing": self.decision.to_dict(),
            "pipeline": self.pipeline,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "planner": self.planner,
            "skill_path": self.skill_path,
            "goal": self.goal,
            "missing_weights": [],
        }


def _normalize_goal(goal: str | None) -> str:
    g = (goal or "").strip().lower()
    aliases = {
        "archival bw": "archival",
        "archival b&w": "archival",
        "b&w": "archival",
        "bw": "archival",
        "black and white": "archival",
        "colourize": "colorize",
        "colorise": "colorize",
        "colourise": "colorize",
        "faces": "portrait",
        "portrait restore": "portrait",
        "scratch": "damaged",
        "scratches": "damaged",
        "damage": "damaged",
        "max quality": "maximum",
        "max": "maximum",
        "hq": "maximum",
    }
    return aliases.get(g, g)


def _node_ready(
    registry: NodeRegistry,
    installed: set[str],
    acknowledged: set[str],
    node_id: str,
    *,
    allow_gated: bool,
) -> bool:
    try:
        node_cls = registry.get_class(node_id)
    except Exception:
        return False
    if node_cls.category is NodeCategory.LEGACY:
        return False
    if node_cls.license.requires_acknowledgement:
        if not allow_gated:
            return False
        if node_id not in acknowledged:
            return False
    return True


def _build_chain_for_goal(
    description: PhotoDescription,
    goal: str,
    *,
    registry: NodeRegistry,
    installed: set[str],
    acknowledged: set[str],
    allow_gated: bool,
) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, str]]]:
    chain: list[str] = []
    params: dict[str, dict[str, Any]] = {}
    reasons: list[dict[str, str]] = []
    deg = set(description.degradations)
    sev = description.severity

    def add(node_id: str, reason: str, node_params: dict[str, Any] | None = None) -> None:
        if node_id in chain:
            return
        if not _node_ready(
            registry, installed, acknowledged, node_id, allow_gated=allow_gated
        ):
            return
        chain.append(node_id)
        if node_params:
            params[node_id] = dict(node_params)
        reasons.append({"node": node_id, "reason": reason})

    low_light = "low_light" in deg or bool(description.profile.get("low_light"))
    if low_light:
        darkir_cls = registry.get_class("darkir")
        darkir_ready = "darkir" in installed and (
            not darkir_cls.license.requires_acknowledgement or "darkir" in acknowledged
        )
        if darkir_ready:
            add("darkir", "low-light — DarkIR preferred when installed + acknowledged")
        else:
            add("exposure_correct", "low-light / underexposure — classical exposure")
    elif description.highlights_blown or "blown_highlights" in deg:
        add(
            "exposure_correct",
            "blown highlights — clip-aware exposure first",
            {"clip_limit": 2.0, "strength": 0.85},
        )

    jpeg_sev = sev.get("jpeg", 0.0)
    if "jpeg" in deg or jpeg_sev >= 0.25:
        qf = 50 if jpeg_sev >= 0.6 else 70 if jpeg_sev >= 0.35 else 80
        add("fbcnn", "JPEG / compression artifacts", {"quality_factor": qf})
    if description.grain_or_noise or "noise" in deg or "grain" in deg:
        if "mambair" in installed:
            add("mambair", "grain / noise — quality denoise+SR when MambaIR installed")

    if goal == "damaged" or description.scratches_likely or "scratches" in deg:
        add(
            "lama",
            "scratches / defects — LaMa (pair with Mask Editor for best results)",
        )

    if goal == "colorize" or (
        description.is_grayscale
        and not description.is_bw_intended
        and goal not in ("archival",)
    ):
        add("ddcolor", "grayscale → colourize (not archival B&W)")

    if goal == "archival" or description.is_bw_intended:
        if "ddcolor" in chain:
            chain.remove("ddcolor")
            params.pop("ddcolor", None)
            reasons[:] = [r for r in reasons if r["node"] != "ddcolor"]
        reasons.append({
            "node": "archival",
            "reason": "archival B&W — skip colour invent; preserve monochrome",
        })

    if description.highlights_blown or "blown_highlights" in deg:
        for cand, reason in (
            ("instructir", "blown highlights — InstructIR finish when installed"),
            ("supir", "blown highlights — SUPIR when InstructIR unavailable"),
        ):
            if cand in chain:
                break
            node_cls = registry.get_class(cand)
            ready = cand in installed and (
                not node_cls.license.requires_acknowledgement or cand in acknowledged
            )
            if ready:
                add(
                    cand,
                    reason,
                    {
                        "prompt_preset": "blown_highlight_rescue",
                        "mode": "finish_only",
                        "mask_highlights": True,
                        "instruction": (
                            "Regenerate natural detail in overexposed and blown-out "
                            "regions; preserve unclipped areas."
                        ),
                    }
                    if cand == "instructir"
                    else None,
                )
                break

    long_edge = max(description.width, description.height)
    if goal == "maximum" and "mambair" in installed:
        add("mambair", "maximum quality — MambaIR upscale")
    elif long_edge < 2500 or "blur" in deg or goal in ("", "portrait", "damaged", "colorize"):
        scale = 4 if long_edge < 1200 else 2
        add("realesrgan", "upscale / sharpen", {"scale": scale})

    if (goal == "portrait" or description.has_faces) and description.face_count >= 1:
        node_cls = registry.get_class("osdface")
        ready = "osdface" in installed and (
            not node_cls.license.requires_acknowledgement or "osdface" in acknowledged
        )
        if ready:
            add("osdface", "faces detected — OSDFace (licence acknowledged)")
        else:
            reasons.append({
                "node": "osdface",
                "reason": (
                    "faces detected — OSDFace available after download + licence ack "
                    "(not on unacked Auto path)"
                ),
            })

    if description.downscale_advice:
        reasons.append({"node": "dpi", "reason": description.downscale_advice})

    if not chain:
        add("realesrgan", "fallback — light upscale", {"scale": 2})

    return chain, params, reasons


def plan_from_description(
    description: PhotoDescription,
    registry: NodeRegistry,
    *,
    goal: str | None = None,
    quality_tier: QualityTier = QualityTier.BALANCED,
    installed: set[str] | None = None,
    acknowledged: set[str] | None = None,
    allow_gated: bool = True,
    hardware: Any = None,
    quality_upscale_ready: bool = False,
    quality_face_ready: bool = False,
) -> AutoPlan:
    goal_n = _normalize_goal(goal)
    installed = installed or set()
    acknowledged = acknowledged or set()

    chain, params, reasons = _build_chain_for_goal(
        description,
        goal_n,
        registry=registry,
        installed=installed,
        acknowledged=acknowledged,
        allow_gated=allow_gated,
    )

    if hardware is not None:
        chain, params = apply_quality_tier(
            chain,
            params,
            quality_tier,
            hardware,
            registry,
            quality_upscale_ready=quality_upscale_ready,
            quality_face_ready=quality_face_ready,
        )

    decision = RoutingDecision(chain=chain, params=params, reasons=reasons)
    spec = auto_order_pipeline(chain, registry, params)
    suggestions = suggest_presets(
        description,
        registry,
        installed=installed,
        acknowledged=acknowledged,
        allow_gated=allow_gated,
        hardware=hardware,
        quality_tier=quality_tier,
        quality_upscale_ready=quality_upscale_ready,
        quality_face_ready=quality_face_ready,
    )
    return AutoPlan(
        description=description,
        decision=decision,
        pipeline=spec.to_dict(),
        suggestions=suggestions,
        planner="skill",
        skill_path=skill_path(),
        goal=goal_n,
    )


_SUGGESTION_GOALS: list[tuple[str, str, str]] = [
    ("", "Auto Restore", "Skill-routed restore for this photo."),
    ("archival", "Archival B&W", "Preserve monochrome — no colour invent."),
    ("colorize", "Colorize", "Restore and colourize a grayscale scan."),
    ("portrait", "Portrait", "Face-aware restore when faces are present."),
    ("damaged", "Damaged Print", "Scratch / defect cleanup plus upscale."),
    ("maximum", "Maximum Quality", "Heavier stack when companions are installed."),
]


def suggest_presets(
    description: PhotoDescription,
    registry: NodeRegistry,
    *,
    installed: set[str] | None = None,
    acknowledged: set[str] | None = None,
    allow_gated: bool = True,
    hardware: Any = None,
    quality_tier: QualityTier = QualityTier.BALANCED,
    quality_upscale_ready: bool = False,
    quality_face_ready: bool = False,
    limit: int = 5,
) -> list[SuggestedPreset]:
    installed = installed or set()
    acknowledged = acknowledged or set()
    out: list[SuggestedPreset] = []

    for goal, name, blurb in _SUGGESTION_GOALS:
        if goal == "colorize" and description.is_bw_intended:
            continue
        if goal == "portrait" and not description.has_faces:
            continue
        if goal == "damaged" and not (
            description.scratches_likely or "scratches" in description.degradations
        ):
            if description.defect_score() < 0.01:
                continue

        chain, params, reasons = _build_chain_for_goal(
            description,
            goal,
            registry=registry,
            installed=installed,
            acknowledged=acknowledged,
            allow_gated=allow_gated,
        )
        if hardware is not None:
            chain, params = apply_quality_tier(
                chain,
                params,
                quality_tier,
                hardware,
                registry,
                quality_upscale_ready=quality_upscale_ready,
                quality_face_ready=quality_face_ready,
            )
        try:
            spec = auto_order_pipeline(chain, registry, params)
        except Exception:
            continue
        summary = description.summary or blurb
        out.append(
            SuggestedPreset(
                name=name,
                description=f"{blurb} {summary}".strip(),
                pipeline=spec.to_dict(),
                reasons=reasons,
                goal=goal,
            )
        )
        if len(out) >= limit:
            break
    return out
