"""Shared fixtures.

The nodes used across the executor/API tests are fakes rather than the real
models on purpose: those tests are about topological order, caching, cancellation
and HTTP status codes, none of which should need a 350MB checkpoint or a GPU to
exercise. The real nodes are covered by their own contract tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from restoration.core.types import (
    BaseRestorationNode,
    ImageArray,
    LicenseInfo,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
    WeightFile,
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "appdata"


@pytest.fixture
def rgb() -> ImageArray:
    rng = np.random.default_rng(1234)
    return rng.random((32, 48, 3), dtype=np.float32)


def make_image(h: int = 32, w: int = 48, c: int = 3, seed: int = 0) -> ImageArray:
    rng = np.random.default_rng(seed)
    return rng.random((h, w, c), dtype=np.float32)


PERMISSIVE = LicenseInfo(spdx_id="Apache-2.0", kind=LicenseKind.PERMISSIVE, source_url="x")
NONCOMMERCIAL = LicenseInfo(
    spdx_id="S-Lab-1.0", kind=LicenseKind.NON_COMMERCIAL, source_url="x"
)


class RecordingNode(BaseRestorationNode):
    """Adds a constant and records every call, so tests can assert on re-runs."""

    id = "recording"
    category = NodeCategory.REGRESSION
    display_name = "Recording"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = False
    param_schema = {
        "type": "object",
        "properties": {"offset": {"type": "number", "default": 0.1}},
    }

    calls: list[str] = []
    loads: list[str] = []
    unloads: list[str] = []

    async def load(self, ctx: RunContext) -> None:
        type(self).loads.append(ctx.node_id)

    def unload(self) -> None:
        type(self).unloads.append(self.id)

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        type(self).calls.append(ctx.node_id)
        ctx.report_progress(0.5, "halfway")
        return np.clip(image + float(params.get("offset", 0.1)), 0.0, 1.0)

    @classmethod
    def reset(cls) -> None:
        cls.calls, cls.loads, cls.unloads = [], [], []


class ScaleNode(BaseRestorationNode):
    """Doubles the image size; proves shape propagation through the DAG."""

    id = "scale2x"
    category = NodeCategory.REGRESSION
    display_name = "Scale 2x"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = False

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        return np.repeat(np.repeat(image, 2, axis=0), 2, axis=1)


class MergeNode(BaseRestorationNode):
    """Averages 'image' and 'image_b' — the branch/merge case."""

    id = "merge"
    category = NodeCategory.ORCHESTRATION
    display_name = "Merge"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = False

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        other = ctx.inputs["image_b"]
        return ((image + other) / 2.0).astype(np.float32)


class OomNode(BaseRestorationNode):
    """Raises CUDA OOM until run with a tile parameter."""

    id = "oom_tileable"
    category = NodeCategory.GENERATIVE
    display_name = "OOM (tileable)"
    license = PERMISSIVE
    vram_tier = VramTier.HIGH
    supports_tiling = True
    uses_gpu = True

    attempts: list[dict] = []

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        type(self).attempts.append(dict(params))
        if not params.get("tile"):
            raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        return image

    @classmethod
    def reset(cls) -> None:
        cls.attempts = []


class OomNoTileNode(BaseRestorationNode):
    """Always OOMs and cannot tile — the unrecoverable path."""

    id = "oom_fatal"
    category = NodeCategory.GENERATIVE
    display_name = "OOM (fatal)"
    license = PERMISSIVE
    vram_tier = VramTier.VERY_HIGH
    supports_tiling = False
    uses_gpu = True

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        raise RuntimeError("CUDA out of memory")


class LowTierGenerativeNode(BaseRestorationNode):
    """A cheaper node in the same category, so fallback_for() has an answer."""

    id = "cheap_generative"
    category = NodeCategory.GENERATIVE
    display_name = "Cheap generative"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = True

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        return image


class SlowNode(BaseRestorationNode):
    """Polls for cancellation between steps, as a real node must."""

    id = "slow"
    category = NodeCategory.REGRESSION
    display_name = "Slow"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = False

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        for _ in range(50):
            ctx.check_cancelled()
            await asyncio.sleep(0.01)
        return image


class FailingNode(BaseRestorationNode):
    id = "boom"
    category = NodeCategory.REGRESSION
    display_name = "Boom"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = False

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        raise ValueError("node exploded")


class NonCommercialNode(BaseRestorationNode):
    id = "gated"
    category = NodeCategory.FACE
    display_name = "Gated"
    license = NONCOMMERCIAL
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest = [
        WeightFile(filename="w.bin", size_bytes=16, url="https://example.invalid/w.bin")
    ]

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        return image


class NeedsWeightsNode(BaseRestorationNode):
    id = "needs_weights"
    category = NodeCategory.REGRESSION
    display_name = "Needs weights"
    license = PERMISSIVE
    vram_tier = VramTier.LOW
    uses_gpu = False
    weight_manifest = [
        WeightFile(filename="w.bin", size_bytes=16, url="https://example.invalid/w.bin")
    ]

    async def run(self, image: ImageArray, params: dict, ctx: RunContext) -> ImageArray:
        return image


ALL_FAKE_NODES: list[type[BaseRestorationNode]] = [
    RecordingNode,
    ScaleNode,
    MergeNode,
    OomNode,
    OomNoTileNode,
    LowTierGenerativeNode,
    SlowNode,
    FailingNode,
    NonCommercialNode,
    NeedsWeightsNode,
]


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    RecordingNode.reset()
    OomNode.reset()


@pytest.fixture
def registry():
    from restoration.core.registry import NodeRegistry

    reg = NodeRegistry()
    for cls in ALL_FAKE_NODES:
        reg.register(cls)
    return reg


@pytest.fixture
def weights(data_dir: Path):
    from restoration.core.weights import WeightManager

    return WeightManager(data_dir / "weights")


@pytest.fixture
def executor(registry, weights):
    from restoration.core.executor import PipelineExecutor

    return PipelineExecutor(registry, weights, device="cpu")
