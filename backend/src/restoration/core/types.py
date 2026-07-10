"""Core types: the RestorationNode contract and everything it references.

This module is the single most important abstraction in the app
(ARCHITECTURE.md section 3): every model — shipped or third-party — implements
``RestorationNode``. Keep this module dependency-light: numpy only, no torch,
no FastAPI, so plugins and tests can import it cheaply.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

# Images flow through the engine as float32, HWC, RGB (or RGBA for matting
# output), values in [0, 1]. One canonical in-memory format everywhere.
ImageArray = np.ndarray


class NodeCategory(str, enum.Enum):
    GENERATIVE = "generative"
    FACE = "face"
    REGRESSION = "regression"
    MASKING = "masking"
    ORCHESTRATION = "orchestration"


class VramTier(str, enum.Enum):
    """VRAM requirement tiers (ARCHITECTURE.md section 5)."""

    LOW = "low"            # < 6 GB
    MID = "mid"            # 6-12 GB
    HIGH = "high"          # 12-24 GB
    VERY_HIGH = "very_high"  # 24 GB+

    @property
    def rank(self) -> int:
        return _TIER_RANK[self]

    @property
    def min_vram_mb(self) -> int:
        return _TIER_MIN_MB[self]


_TIER_RANK = {
    VramTier.LOW: 0,
    VramTier.MID: 1,
    VramTier.HIGH: 2,
    VramTier.VERY_HIGH: 3,
}
_TIER_MIN_MB = {
    VramTier.LOW: 0,
    VramTier.MID: 6 * 1024,
    VramTier.HIGH: 12 * 1024,
    VramTier.VERY_HIGH: 24 * 1024,
}


class LicenseKind(str, enum.Enum):
    PERMISSIVE = "permissive"          # Apache/MIT/BSD — safe to bundle & default
    NON_COMMERCIAL = "non_commercial"  # runnable locally, opt-in only
    UNCLEAR = "unclear"                # no LICENSE found — do not ship as default
    CUSTOM = "custom"


@dataclass(frozen=True)
class LicenseInfo:
    """License metadata surfaced in the UI *before* any download starts.

    MODEL_STACK.md's licensing tiers are binding: anything not permissive
    requires an explicit acknowledgement gate (ARCHITECTURE.md section 6).
    """

    spdx_id: str            # e.g. "Apache-2.0", "BSD-3-Clause", "S-Lab-1.0"
    kind: LicenseKind
    source_url: str         # where the license claim was verified

    @property
    def requires_acknowledgement(self) -> bool:
        return self.kind is not LicenseKind.PERMISSIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "spdx_id": self.spdx_id,
            "kind": self.kind.value,
            "source_url": self.source_url,
            "requires_acknowledgement": self.requires_acknowledgement,
        }


@dataclass(frozen=True)
class WeightFile:
    """One downloadable weight file in a node's manifest.

    Exactly one source must be set: either ``url`` or (``hf_repo_id`` +
    ``hf_filename``). ``sha256`` may be None for sources that don't publish
    one — the WeightManager then pins the hash on first download (TOFU) and
    verifies against the pinned value forever after; it never *skips*
    verification silently.
    """

    filename: str
    size_bytes: int
    sha256: str | None = None
    url: str | None = None
    hf_repo_id: str | None = None
    hf_filename: str | None = None

    def __post_init__(self) -> None:
        from_url = self.url is not None
        from_hf = self.hf_repo_id is not None and self.hf_filename is not None
        if from_url == from_hf:
            raise ValueError(
                f"WeightFile '{self.filename}': exactly one of url or "
                f"(hf_repo_id, hf_filename) must be set"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ImageMeta:
    """Cheap metadata a node can use in supports() without touching pixels."""

    width: int
    height: int
    channels: int

    @classmethod
    def from_array(cls, image: ImageArray) -> ImageMeta:
        h, w = image.shape[:2]
        c = 1 if image.ndim == 2 else image.shape[2]
        return cls(width=w, height=h, channels=c)


# ---------------------------------------------------------------------------
# Progress events — one shape for the whole app (ARCHITECTURE.md section 2).
# ---------------------------------------------------------------------------

class NodeStatus(str, enum.Enum):
    QUEUED = "queued"
    LOADING_WEIGHTS = "loading_weights"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class ProgressEvent:
    """Structured progress event streamed over the per-job WebSocket."""

    node_id: str                       # pipeline-instance id ("" for job-level)
    status: NodeStatus
    progress: float = 0.0              # 0.0-1.0
    message: str | None = None
    preview_url: str | None = None
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "progress": round(float(self.progress), 4),
            "message": self.message,
            "preview_url": self.preview_url,
            "cached": self.cached,
        }


EventCallback = Callable[[ProgressEvent], None]


@dataclass
class RunContext:
    """What a node gets at run time.

    Gives a node a way to emit intermediate previews and progress fractions
    back through the WebSocket stream without knowing anything about HTTP or
    the UI (ARCHITECTURE.md section 3).

    ``inputs`` carries *all* upstream outputs keyed by the edge's ``to_input``
    name. The primary input (``to_input == "image"``) is also passed as the
    ``image`` argument to run(); merge-style orchestration nodes read the rest
    (e.g. "image_b", "mask") from here.
    """

    job_id: str
    node_id: str
    device: str = "cpu"                       # "cpu" | "cuda" | "cuda:N" | "mps"
    weights_dir: str | None = None            # node's installed weights, if any
    inputs: dict[str, ImageArray] = field(default_factory=dict)
    _emit: EventCallback | None = None
    _is_cancelled: Callable[[], bool] | None = None
    _preview_sink: Callable[[ImageArray], str | None] | None = None

    def report_progress(self, fraction: float, message: str | None = None) -> None:
        if self._emit is not None:
            self._emit(ProgressEvent(
                node_id=self.node_id,
                status=NodeStatus.RUNNING,
                progress=max(0.0, min(1.0, fraction)),
                message=message,
            ))

    def send_preview(self, image: ImageArray, fraction: float = 0.0) -> None:
        url = self._preview_sink(image) if self._preview_sink else None
        if self._emit is not None:
            self._emit(ProgressEvent(
                node_id=self.node_id,
                status=NodeStatus.RUNNING,
                progress=max(0.0, min(1.0, fraction)),
                preview_url=url,
            ))

    def check_cancelled(self) -> None:
        """Nodes should call this between expensive steps (e.g. tiles)."""
        from .errors import JobCancelled  # noqa: PLC0415 (avoids an import cycle)
        if self._is_cancelled is not None and self._is_cancelled():
            raise JobCancelled(f"job {self.job_id} was cancelled")


# ---------------------------------------------------------------------------
# The node contract.
# ---------------------------------------------------------------------------

@runtime_checkable
class RestorationNode(Protocol):
    """Every model — in-box or plugin — implements this (ARCHITECTURE.md §3)."""

    id: str
    category: NodeCategory
    display_name: str
    license: LicenseInfo
    vram_tier: VramTier
    param_schema: dict[str, Any]        # JSON Schema; drives the Inspector form
    weight_manifest: list[WeightFile]

    def supports(self, image: ImageMeta) -> bool: ...

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray: ...


class BaseRestorationNode:
    """Convenience base class implementing the protocol's boilerplate.

    Subclasses set the class attributes and implement ``run``. ``load`` /
    ``unload`` bracket weight residency in (V)RAM: the executor calls
    ``unload`` immediately after a node completes unless the user pinned it
    (ARCHITECTURE.md section 4).
    """

    id: str = ""
    category: NodeCategory = NodeCategory.ORCHESTRATION
    display_name: str = ""
    description: str = ""
    license: LicenseInfo = LicenseInfo(
        spdx_id="Apache-2.0", kind=LicenseKind.PERMISSIVE, source_url=""
    )
    vram_tier: VramTier = VramTier.LOW
    param_schema: dict[str, Any] = {"type": "object", "properties": {}}
    weight_manifest: list[WeightFile] = []
    # True if the node can process in tiles when full-frame OOMs
    # (drives the executor's OOM fallback path).
    supports_tiling: bool = False
    # False for pure-CPU orchestration nodes: they skip the GPU semaphore.
    uses_gpu: bool = True

    def supports(self, image: ImageMeta) -> bool:  # noqa: ARG002
        return True

    async def load(self, ctx: RunContext) -> None:
        """Load weights into (V)RAM. Idempotent."""

    def unload(self) -> None:
        """Release weights from (V)RAM. Idempotent."""

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------

    def default_params(self) -> dict[str, Any]:
        """Defaults extracted from param_schema."""
        out: dict[str, Any] = {}
        for name, spec in self.param_schema.get("properties", {}).items():
            if isinstance(spec, dict) and "default" in spec:
                out[name] = spec["default"]
        return out

    def describe(self) -> dict[str, Any]:
        """Serializable description for GET /api/nodes and `restore nodes`."""
        return {
            "id": self.id,
            "category": self.category.value,
            "display_name": self.display_name,
            "description": self.description,
            "license": self.license.to_dict(),
            "vram_tier": self.vram_tier.value,
            "param_schema": self.param_schema,
            "weight_manifest": [w.to_dict() for w in self.weight_manifest],
            "supports_tiling": self.supports_tiling,
            "uses_gpu": self.uses_gpu,
        }


def params_hash(params: dict[str, Any]) -> str:
    """Stable hash of a params dict, for the executor's output cache."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def array_hash(image: ImageArray) -> str:
    """Content hash of an image array, for the executor's output cache."""
    h = hashlib.sha256()
    h.update(str(image.shape).encode())
    h.update(str(image.dtype).encode())
    h.update(np.ascontiguousarray(image).tobytes())
    return h.hexdigest()
