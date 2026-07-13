"""Exposure recovery (ROADMAP.md Phase 4.5.1) — a classical CLAHE + auto-gamma
node, verified against real recovered detail and brightness, not just "it
doesn't crash." Needs opencv (part of the [inference] extra); skips cleanly
without it, same pattern as test_tiling.py's torch dependency."""

from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2", reason="exposure correction needs opencv, part of [inference]")

from restoration.core.types import RunContext  # noqa: E402
from restoration.nodes.exposure import ExposureCorrectNode  # noqa: E402


def _textured_image(mean: float, seed: int = 0) -> np.ndarray:
    """A synthetic image with real local texture (not a smooth analytic
    gradient, which CLAHE handles poorly since each tile then has almost no
    local histogram spread to work with)."""
    rng = np.random.default_rng(seed)
    base = rng.random((128, 128), dtype=np.float32)
    # Low-pass a bit so it reads as "photo-like" texture, not pure noise.
    kernel = np.ones((5, 5), dtype=np.float32) / 25.0
    textured = cv2.filter2D(base, -1, kernel)
    textured = (textured - textured.mean()) * 0.5 + mean
    textured = np.clip(textured, 0.0, 1.0)
    return np.stack([textured] * 3, axis=-1).astype(np.float32)


@pytest.fixture
def ctx() -> RunContext:
    return RunContext(job_id="t", node_id="exposure_correct", device="cpu")


async def test_underexposed_image_gets_brighter_and_more_locally_detailed(ctx):
    dark = _textured_image(mean=0.08)
    out = await ExposureCorrectNode().run(dark, {}, ctx)
    assert out.mean() > dark.mean() * 2
    assert out.std() > dark.std()


async def test_overexposed_image_gets_darker_and_more_locally_detailed(ctx):
    bright = _textured_image(mean=0.92)
    out = await ExposureCorrectNode().run(bright, {}, ctx)
    assert out.mean() < bright.mean()
    assert out.std() > bright.std()


async def test_well_exposed_image_is_not_pushed_toward_an_extreme(ctx):
    """CLAHE is a nonlinear local operation, not a mean-preserving one, so a
    well-exposed image still shifts some even when there's nothing wrong to
    fix (measured empirically, not an invented promise) — but it must not
    swing toward over- or under-exposed. In the real Simple Mode pipeline
    this node is rule-table-gated to only run when low_light or
    blown_highlights was actually detected; the `strength` param is the
    safety valve for anyone reaching for it directly in Advanced Mode."""
    normal = _textured_image(mean=0.5)
    out = await ExposureCorrectNode().run(normal, {}, ctx)
    assert 0.3 < out.mean() < 0.7


async def test_strength_zero_is_a_pass_through(ctx):
    dark = _textured_image(mean=0.1)
    out = await ExposureCorrectNode().run(dark, {"strength": 0.0}, ctx)
    assert np.allclose(out, np.clip(dark, 0.0, 1.0), atol=1e-5)


async def test_alpha_channel_is_preserved(ctx):
    dark = _textured_image(mean=0.1)
    rgba = np.concatenate([dark, np.full((128, 128, 1), 0.7, dtype=np.float32)], axis=2)
    out = await ExposureCorrectNode().run(rgba, {}, ctx)
    assert out.shape == (128, 128, 4)
    assert np.allclose(out[..., 3], 0.7)


def test_node_declares_no_weights_and_no_gpu():
    node = ExposureCorrectNode()
    assert node.weight_manifest == []
    assert node.uses_gpu is False
