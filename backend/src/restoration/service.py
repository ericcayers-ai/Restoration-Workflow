"""Application services: the one place the engine's pieces are wired together.

The API layer, the CLI and the tests all build an ``AppServices`` and then talk
to the engine through it, so there is exactly one definition of "a configured
backend" and no route can quietly construct a differently-configured executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .builtin_presets import (
    builtin_preset_names as _builtin_preset_names,
    seed_builtin_presets as _seed_builtin_presets,
)
from .core.analyzer import DegradationAnalyzer, DegradationProfile
from .core.auto_plan import AutoPlan, plan_from_description, suggest_presets
from .core.executor import PipelineExecutor, PipelineSpec
from .core.hardware import HardwareDetector, HardwareInfo
from .core.ordering import auto_order_pipeline
from .core.quality import QualityTier, apply_quality_tier
from .core.registry import NodeRegistry
from .core.rules import RoutingDecision, RuleTable
from .core.types import ImageArray
from .core.vlm import PhotoDescription, VlmManager
from .core.weights import WeightManager, default_data_dir
from .presets import PresetStore


@dataclass(frozen=True)
class AutoPipeline:
    """What Simple Mode decided, and why — all of it inspectable.

    The ``reasons`` are surfaced to the user rather than kept for debugging: the
    promise is an *inspectable* heuristic, not an opaque one that happens to be
    simple underneath.
    """

    profile: DegradationProfile
    decision: RoutingDecision
    spec: PipelineSpec

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "routing": self.decision.to_dict(),
            "pipeline": self.spec.to_dict(),
        }


class AppServices:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        plugins_dir: Path | None = None,
        rule_table: RuleTable | None = None,
        force_cpu: bool | None = None,
        gpu_slots: int | None = None,
        seed_builtin_presets: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.plugins_dir = Path(plugins_dir) if plugins_dir else self.data_dir / "plugins"

        self.registry = NodeRegistry()
        self.registry.register_builtins()
        self.registry.discover_plugins(self.plugins_dir)

        self.weights = WeightManager(self.data_dir / "weights")
        self.masks_dir = self.data_dir / "masks"
        self.masks_dir.mkdir(parents=True, exist_ok=True)
        self.vlm = VlmManager(self.data_dir / "weights" / "vlm")
        self.hardware = HardwareDetector(force_cpu=force_cpu)
        self.analyzer = DegradationAnalyzer()
        self.presets = PresetStore(self.data_dir / "presets")
        if seed_builtin_presets:
            _seed_builtin_presets(self.presets, self.registry)

        self.rule_table = rule_table or RuleTable.load_default()
        # Fails loudly at startup rather than mid-run if the default auto-pipeline
        # ever references a missing or non-permissively-licensed node.
        self.rule_table.validate(self.registry)

        info = self.hardware.detect()
        self.executor = PipelineExecutor(
            self.registry,
            self.weights,
            device=info.device_string,
            gpu_slots=self._gpu_slots(info, gpu_slots),
            data_dir=str(self.data_dir),
        )

    @staticmethod
    def _gpu_slots(info: HardwareInfo, override: int | None) -> int:
        if override is not None:
            return max(1, override)
        return 1  # multi-GPU concurrency is opt-in (ARCHITECTURE.md section 2)

    # -- node & hardware views ------------------------------------------------

    def describe_nodes(self) -> list[dict[str, Any]]:
        """Everything the Model Stack rail needs: contract, licence, VRAM gate,
        and whether the weights are on disk."""
        out = []
        for node in self.registry.all_nodes():
            described = node.describe()
            described["availability"] = self.hardware.availability(
                node.vram_tier, node.uses_gpu
            ).to_dict()
            described["weights"] = self.weights.status(node).to_dict()
            out.append(described)
        return out

    def describe_node(self, node_id: str) -> dict[str, Any]:
        node = self.registry.create(node_id)
        described = node.describe()
        described["availability"] = self.hardware.availability(
            node.vram_tier, node.uses_gpu
        ).to_dict()
        described["weights"] = self.weights.status(node).to_dict()
        return described

    # -- Simple Mode ----------------------------------------------------------

    def analyze(
        self, image: ImageArray, quality_tier: QualityTier = QualityTier.BALANCED
    ) -> AutoPipeline:
        profile = self.analyzer.analyze(image)
        decision = self.rule_table.route(profile)
        chain, params = apply_quality_tier(
            decision.chain,
            decision.params,
            quality_tier,
            self.hardware.detect(),
            self.registry,
            quality_upscale_ready=self.weights.is_installed(self.registry.create("mambair")),
            quality_face_ready=self.weights.is_installed(
                self.registry.create("osdface")
            ),
        )
        chain, params, extra_reasons = self._apply_companion_overlays(profile, chain, params)
        reasons = list(decision.reasons) + extra_reasons
        decision = RoutingDecision(chain=chain, params=params, reasons=reasons)
        spec = auto_order_pipeline(chain, self.registry, params)
        return AutoPipeline(profile=profile, decision=decision, spec=spec)

    def _node_ready(self, node_id: str) -> bool:
        """Installed (+ licence acked when required)."""
        try:
            node = self.registry.create(node_id)
        except Exception:
            return False
        if not node.weight_manifest:
            return True
        if not self.weights.is_installed(node):
            return False
        if node.license.requires_acknowledgement and not self.weights.is_acknowledged(node_id):
            return False
        return True

    def _apply_companion_overlays(
        self,
        profile: DegradationProfile,
        chain: list[str],
        params: dict[str, dict[str, Any]],
    ) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, str]]]:
        """Prefer DarkIR / InstructIR / SUPIR / OSDFace companions when ready.

        Never puts gated models into ``rule_table.json``; overlays only when the
        user already installed (+acked) the companion weights.
        """
        chain = list(chain)
        params = {k: dict(v) for k, v in params.items()}
        reasons: list[dict[str, str]] = []

        def insert_after(anchor: str, node_id: str) -> None:
            if node_id in chain:
                return
            if anchor in chain:
                chain.insert(chain.index(anchor) + 1, node_id)
            else:
                chain.insert(0, node_id)

        def replace(old: str, new: str) -> None:
            if old in chain and new not in chain:
                chain[chain.index(old)] = new
                if old in params:
                    params[new] = params.pop(old)

        # Low-light: DarkIR prefers over classical exposure when ready.
        if profile.low_light and self._node_ready("darkir"):
            if "exposure_correct" in chain:
                replace("exposure_correct", "darkir")
                reasons.append({
                    "node": "darkir",
                    "reason": "low-light — DarkIR installed; preferred over classical exposure",
                })
            elif "darkir" not in chain:
                chain.insert(0, "darkir")
                reasons.append({
                    "node": "darkir",
                    "reason": "low-light — DarkIR companion overlay",
                })
        elif profile.low_light and self._node_ready("instructir") and "instructir" not in chain:
            if "exposure_correct" in chain:
                anchor = "exposure_correct"
            else:
                anchor = chain[0] if chain else ""
            if anchor:
                insert_after(anchor, "instructir")
            else:
                chain.append("instructir")
            params.setdefault("instructir", {})
            params["instructir"].update({
                "prompt_preset": "low_light_lift",
                "mode": "finish_only",
                "instruction": (
                    "Brighten underexposed areas, reduce crushed shadows, "
                    "and control amplified noise."
                ),
            })
            reasons.append({
                "node": "instructir",
                "reason": "low-light — InstructIR companion overlay",
            })

        # Severe blown highlights: InstructIR → SUPIR (if ready).
        severe_clip = profile.blown_highlights and (
            profile.clip_fraction >= 0.04 or profile.over_exposure >= 0.55
        )
        if severe_clip:
            companion = None
            for cand in ("instructir", "supir"):
                if self._node_ready(cand):
                    companion = cand
                    break
            if companion and companion not in chain:
                if "exposure_correct" in chain:
                    insert_after("exposure_correct", companion)
                elif chain:
                    insert_after(chain[0], companion)
                else:
                    chain.append(companion)
                if companion == "instructir":
                    params.setdefault("instructir", {})
                    params["instructir"].update({
                        "prompt_preset": "blown_highlight_rescue",
                        "mode": "finish_only",
                        "mask_highlights": True,
                        "instruction": (
                            "Regenerate natural detail in overexposed and blown-out "
                            "regions; preserve unclipped areas."
                        ),
                    })
                reasons.append({
                    "node": companion,
                    "reason": (
                        f"severe blown highlights (clip={profile.clip_fraction:.3f}) — "
                        f"{companion} companion overlay"
                    ),
                })

        # Faces: OSDFace only (gated), when weights are installed + acknowledged.
        if (
            profile.face_count is not None
            and profile.face_count >= 1
            and self._node_ready("osdface")
            and "osdface" not in chain
        ):
            chain.append("osdface")
            reasons.append({
                "node": "osdface",
                "reason": "faces detected — OSDFace companion overlay (licence acknowledged)",
            })

        return chain, params, reasons

    def build_ensemble(
        self,
        image: ImageArray | None = None,
        *,
        prompt_preset_id: str | None = None,
        instruction: str | None = None,
        mode: str = "guide_and_finish",
        profile: DegradationProfile | None = None,
        profile_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .core.ensemble import build_guided_ensemble  # noqa: PLC0415

        if profile is None and profile_dict is not None:
            profile = DegradationProfile.from_dict(profile_dict)
        if profile is None and image is not None:
            profile = self.analyzer.analyze(image)
        installed = {
            n.id for n in self.registry.all_nodes() if self.weights.is_installed(n)
        }
        acked = {
            n.id
            for n in self.registry.all_nodes()
            if n.license.requires_acknowledgement and self.weights.is_acknowledged(n.id)
        }
        plan = build_guided_ensemble(
            profile,
            registry=self.registry,
            prompt_preset_id=prompt_preset_id,
            instruction=instruction,
            mode=mode,
            installed=installed,
            acknowledged=acked,
        )
        return plan.to_dict()

    def missing_weights(self, spec: PipelineSpec) -> list[str]:
        """Node types in ``spec`` whose required weights for their params aren't installed."""
        missing = []
        for node_spec in spec.nodes:
            node = self.registry.create(node_spec.type)
            params = {**node.default_params(), **node_spec.params}
            if not self.weights.is_installed(node, params):
                if node_spec.type not in missing:
                    missing.append(node_spec.type)
        return missing

    def unacknowledged_nodes(self, spec: PipelineSpec) -> list[str]:
        """Gated node types in ``spec`` that still need a licence acknowledgement."""
        seen: list[str] = []
        for node_spec in spec.nodes:
            node = self.registry.create(node_spec.type)
            if (
                node.license.requires_acknowledgement
                and not self.weights.is_acknowledged(node_spec.type)
                and node_spec.type not in seen
            ):
                seen.append(node_spec.type)
        return seen

    def preset_licence_gate(self, pipeline: dict[str, Any]) -> dict[str, Any]:
        """Licence readiness for a preset/pipeline document (Simple Mode gate)."""
        from .core.executor import parse_pipeline  # noqa: PLC0415

        spec = parse_pipeline(pipeline, self.registry)
        unacked = self.unacknowledged_nodes(spec)
        return {
            "ready": not unacked,
            "unacknowledged_node_ids": unacked,
            "missing_weights": self.missing_weights(spec),
        }

    def describe_preset(self, preset: Any) -> dict[str, Any]:
        """Preset JSON plus licence/weight gate fields for Simple Mode filtering."""
        payload = preset.to_dict() if hasattr(preset, "to_dict") else dict(preset)
        gate = self.preset_licence_gate(payload["pipeline"])
        payload["licence"] = gate
        payload["builtin"] = payload.get("name") in set(_builtin_preset_names())
        return payload

    # -- VLM Auto (Phase 4) ---------------------------------------------------

    def _installed_ids(self) -> set[str]:
        return {n.id for n in self.registry.all_nodes() if self.weights.is_installed(n)}

    def _acknowledged_ids(self) -> set[str]:
        return {
            n.id
            for n in self.registry.all_nodes()
            if n.license.requires_acknowledgement and self.weights.is_acknowledged(n.id)
        }

    def describe_photo(
        self,
        image: ImageArray,
        *,
        force_heuristic: bool = False,
    ) -> PhotoDescription:
        return self.vlm.describe_photo(image, force_heuristic=force_heuristic)

    def plan_auto(
        self,
        image: ImageArray,
        *,
        goal: str | None = None,
        quality_tier: QualityTier = QualityTier.BALANCED,
        fallback: str = "skill",
        force_heuristic: bool = False,
    ) -> dict[str, Any]:
        """VLM/heuristic describe + skill rules, or pure rule_table fallback."""
        if fallback == "rule_table":
            auto = self.analyze(image, quality_tier)
            payload = auto.to_dict()
            payload["planner"] = "rule_table"
            payload["description"] = self.describe_photo(
                image, force_heuristic=True
            ).to_dict()
            payload["suggestions"] = []
            payload["goal"] = (goal or "").strip().lower()
            payload["skill_path"] = None
            payload["missing_weights"] = self.missing_weights(auto.spec)
            payload["vlm"] = self.vlm.status()
            return payload

        description = self.describe_photo(image, force_heuristic=force_heuristic)
        plan = plan_from_description(
            description,
            self.registry,
            goal=goal,
            quality_tier=quality_tier,
            installed=self._installed_ids(),
            acknowledged=self._acknowledged_ids(),
            allow_gated=True,
            hardware=self.hardware.detect(),
            quality_upscale_ready=self.weights.is_installed(
                self.registry.create("mambair")
            ),
            quality_face_ready=self.weights.is_installed(self.registry.create("osdface")),
        )
        profile = (
            DegradationProfile.from_dict(description.profile)
            if description.profile
            else self.analyzer.analyze(image)
        )
        chain, params, extra = self._apply_companion_overlays(
            profile, list(plan.decision.chain), dict(plan.decision.params)
        )
        if extra:
            reasons = list(plan.decision.reasons) + extra
            decision = RoutingDecision(chain=chain, params=params, reasons=reasons)
            spec = auto_order_pipeline(chain, self.registry, params)
            plan = AutoPlan(
                description=plan.description,
                decision=decision,
                pipeline=spec.to_dict(),
                suggestions=plan.suggestions,
                planner=plan.planner,
                skill_path=plan.skill_path,
                goal=plan.goal,
            )
        payload = plan.to_dict()
        from .core.executor import parse_pipeline  # noqa: PLC0415

        spec = parse_pipeline(plan.pipeline, self.registry)
        payload["missing_weights"] = self.missing_weights(spec)
        payload["vlm"] = self.vlm.status()
        return payload

    def suggest_auto_presets(
        self,
        image: ImageArray,
        *,
        goal: str | None = None,
        force_heuristic: bool = False,
    ) -> dict[str, Any]:
        description = self.describe_photo(image, force_heuristic=force_heuristic)
        suggestions = suggest_presets(
            description,
            self.registry,
            installed=self._installed_ids(),
            acknowledged=self._acknowledged_ids(),
            allow_gated=True,
            hardware=self.hardware.detect(),
            quality_upscale_ready=self.weights.is_installed(
                self.registry.create("mambair")
            ),
            quality_face_ready=self.weights.is_installed(self.registry.create("osdface")),
        )
        if goal:
            g = goal.strip().lower()
            suggestions = sorted(
                suggestions,
                key=lambda s: 0 if s.goal == g or (not g and not s.goal) else 1,
            )
        return {
            "description": description.to_dict(),
            "suggestions": [s.to_dict() for s in suggestions],
            "vlm": self.vlm.status(),
            "user_presets": [
                self.describe_preset(p)
                for p in self.presets.list()
                if p.name not in set(_builtin_preset_names())
            ],
        }

    def weight_download_totals(self) -> dict[str, Any]:
        """Bytes / counts for missing *default-variant* permissive vs restricted weights."""
        permissive_bytes = restricted_bytes = 0
        permissive_n = restricted_n = 0
        missing_ids: list[str] = []
        for node in self.registry.all_nodes():
            if not node.weight_manifest:
                continue
            if self.weights.is_installed(node):
                continue
            status = self.weights.status(node)
            size = status.missing_size_bytes
            missing_ids.append(node.id)
            if node.license.requires_acknowledgement:
                restricted_bytes += size
                restricted_n += 1
            else:
                permissive_bytes += size
                permissive_n += 1
        return {
            "missing_node_ids": missing_ids,
            "permissive": {"count": permissive_n, "bytes": permissive_bytes},
            "restricted": {"count": restricted_n, "bytes": restricted_bytes},
            "grand": {
                "count": permissive_n + restricted_n,
                "bytes": permissive_bytes + restricted_bytes,
            },
        }
