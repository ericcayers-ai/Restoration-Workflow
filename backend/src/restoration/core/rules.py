"""Rule table: DegradationProfile -> default node chain.

The table is a plain data file (core/data/rule_table.json), not hardcoded
logic, so Phase 5 can evolve it — e.g. replacing rule lookup with a learned
router — without touching the executor (ARCHITECTURE.md section 4).

Format (version 1) — an ordered list of *stages*; each stage appends its node
to the chain when all of its conditions match the profile's metrics:

    {
      "version": 1,
      "fallback_chain": ["realesrgan"],
      "stages": [
        {"node": "fbcnn",
         "when": {"jpeg_blockiness": {"gte": 0.12}},
         "params": {},
         "reason": "visible JPEG block artifacts"},
        ...
      ]
    }

Condition operators: gte, gt, lte, lt, eq, is (bool). A condition on a metric
whose value is null (e.g. face_count with no detector installed) never
matches — absence of evidence is not evidence.

Every node referenced here must be permissively licensed: Simple Mode's
default pipeline must never silently depend on a non-commercial-only model
(ROADMAP.md guardrails; enforced by RuleTable.validate()).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from .analyzer import DegradationProfile
from .errors import PipelineValidationError
from .registry import NodeRegistry

_OPERATORS = {
    "gte": lambda v, t: v >= t,
    "gt": lambda v, t: v > t,
    "lte": lambda v, t: v <= t,
    "lt": lambda v, t: v < t,
    "eq": lambda v, t: v == t,
    "is": lambda v, t: bool(v) is bool(t),
}


@dataclass(frozen=True)
class Stage:
    node: str
    when: dict[str, dict[str, Any]]
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def matches(self, metrics: dict[str, Any]) -> bool:
        for metric, conditions in self.when.items():
            value = metrics.get(metric)
            if value is None:
                return False
            for op, threshold in conditions.items():
                fn = _OPERATORS.get(op)
                if fn is None:
                    raise PipelineValidationError(
                        f"rule table: unknown operator '{op}' on metric '{metric}'"
                    )
                if not fn(value, threshold):
                    return False
        return True


@dataclass
class RoutingDecision:
    chain: list[str]
    params: dict[str, dict[str, Any]]
    reasons: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {"chain": self.chain, "params": self.params, "reasons": self.reasons}


class RuleTable:
    def __init__(self, data: dict[str, Any]):
        if data.get("version") != 1:
            raise PipelineValidationError(
                f"unsupported rule table version {data.get('version')!r}"
            )
        self.stages = [
            Stage(
                node=raw["node"],
                when=raw.get("when", {}),
                params=raw.get("params", {}),
                reason=raw.get("reason", ""),
            )
            for raw in data.get("stages", [])
        ]
        self.fallback_chain: list[str] = list(data.get("fallback_chain", []))
        if not self.fallback_chain:
            raise PipelineValidationError("rule table needs a non-empty fallback_chain")

    @classmethod
    def load_default(cls) -> RuleTable:
        text = (
            resources.files("restoration.core") / "data" / "rule_table.json"
        ).read_text(encoding="utf-8")
        return cls(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> RuleTable:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def validate(self, registry: NodeRegistry) -> None:
        """Every referenced node must exist, be permissive, and not Legacy."""
        from .types import NodeCategory  # noqa: PLC0415 (avoid import cycle at module load)

        for node_id in {s.node for s in self.stages} | set(self.fallback_chain):
            node_cls = registry.get_class(node_id)  # raises on unknown
            if node_cls.category is NodeCategory.LEGACY:
                raise PipelineValidationError(
                    f"rule table references legacy node '{node_id}' — Simple Mode "
                    f"Auto must not route to Settings → Legacy models"
                )
            if node_cls.license.requires_acknowledgement:
                raise PipelineValidationError(
                    f"rule table references '{node_id}' whose license "
                    f"('{node_cls.license.spdx_id}') is not permissive — the default "
                    f"auto-pipeline must never depend on a non-permissive model"
                )

    def route(self, profile: DegradationProfile) -> RoutingDecision:
        metrics = profile.metrics()
        chain: list[str] = []
        params: dict[str, dict[str, Any]] = {}
        reasons: list[dict[str, str]] = []
        for stage in self.stages:
            if stage.node in chain:
                continue
            if stage.matches(metrics):
                chain.append(stage.node)
                if stage.params:
                    params[stage.node] = dict(stage.params)
                reasons.append({"node": stage.node, "reason": stage.reason})
        if not chain:
            chain = list(self.fallback_chain)
            reasons.append({
                "node": ",".join(chain),
                "reason": "no specific degradation detected; default enhancement chain",
            })
        return RoutingDecision(chain=chain, params=params, reasons=reasons)
