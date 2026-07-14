"""Regression corpus smoke test (ROADMAP.md Phase 9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from restoration.core.analyzer import DegradationAnalyzer
from restoration.core.images import load_image
from restoration.core.types import RunContext
from restoration.nodes import MaskFromImageNode

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"


@pytest.fixture
def ctx() -> RunContext:
    return RunContext(job_id="corpus", node_id="n", device="cpu")


@pytest.fixture(scope="module", autouse=True)
def ensure_corpus():
    import importlib.util

    script = CORPUS_DIR / "generate_corpus.py"
    spec = importlib.util.spec_from_file_location("generate_corpus", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    if not any(CORPUS_DIR.glob("*.png")):
        mod.generate_corpus(CORPUS_DIR)


@pytest.mark.parametrize("image_path", sorted(CORPUS_DIR.glob("*.png")), ids=lambda p: p.stem)
def test_analyzer_runs_on_corpus_image(image_path: Path):
    image = load_image(image_path)
    profile = DegradationAnalyzer().analyze(image)
    assert profile.width > 0 and profile.height > 0


@pytest.mark.asyncio
async def test_old_photos_scratch_on_corpus(ctx):
    pytest.importorskip("cv2", reason="old_photos_scratch needs opencv, part of [inference]")
    from restoration.nodes import OldPhotosScratchNode

    node = OldPhotosScratchNode()
    for image_path in CORPUS_DIR.glob("*.png"):
        image = load_image(image_path)
        out = await node.run(image, {}, ctx)
        assert out.shape == image.shape


@pytest.mark.asyncio
async def test_defect_mask_on_corpus(ctx):
    node = MaskFromImageNode()
    image = load_image(next(CORPUS_DIR.glob("*.png")))
    mask = await node.run(image, {"source": "defect"}, ctx)
    assert mask.ndim == 3
