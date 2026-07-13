"""Application services: the one place the engine's pieces are wired together.

The API layer, the CLI and the tests all build an ``AppServices`` and then talk
to the engine through it, so there is exactly one definition of "a configured
backend" and no route can quietly construct a differently-configured executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.analyzer import DegradationAnalyzer, DegradationProfile
from .core.executor import PipelineExecutor, PipelineSpec
from .core.ordering import auto_order_pipeline
from .core.hardware import HardwareDetector, HardwareInfo
from .core.quality import QualityTier, apply_quality_tier
from .core.registry import NodeRegistry
from .core.rules import RoutingDecision, RuleTable
from .core.types import ImageArray
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
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.plugins_dir = Path(plugins_dir) if plugins_dir else self.data_dir / "plugins"

        self.registry = NodeRegistry()
        self.registry.register_builtins()
        self.registry.discover_plugins(self.plugins_dir)

        self.weights = WeightManager(self.data_dir / "weights")
        self.hardware = HardwareDetector(force_cpu=force_cpu)
        self.analyzer = DegradationAnalyzer()
        self.presets = PresetStore(self.data_dir / "presets")

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
            quality_upscale_ready=self.weights.is_installed(self.registry.create("swinir")),
            quality_face_ready=self.weights.is_installed(
                self.registry.create("restoreformer")
            ),
        )
        decision = RoutingDecision(chain=chain, params=params, reasons=decision.reasons)
        spec = auto_order_pipeline(chain, self.registry, params)
        return AutoPipeline(profile=profile, decision=decision, spec=spec)

    def missing_weights(self, spec: PipelineSpec) -> list[str]:
        """Node types in ``spec`` whose weights aren't installed yet."""
        missing = []
        for node_type in dict.fromkeys(n.type for n in spec.nodes):
            node = self.registry.create(node_type)
            if not self.weights.is_installed(node):
                missing.append(node_type)
        return missing
