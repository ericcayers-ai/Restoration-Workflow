"""Phase 3 — real inpaint masks, load_mask node, mask asset API, mask-weighted blend."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from restoration.api.app import create_app
from restoration.core.errors import NodeExecutionError
from restoration.core.types import RunContext
from restoration.nodes import BlendNode, LoadMaskNode
from restoration.nodes.inference.diffusion_runtime import resolve_inpaint_mask
from restoration.service import AppServices

from .conftest import ALL_FAKE_NODES


def _rgb(h: int = 16, w: int = 16, value: float = 0.5) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.float32)


def _mask(h: int = 16, w: int = 16, value: float = 1.0) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.float32)


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    return RunContext(
        node_id="test",
        job_id="job",
        weights_dir=str(tmp_path),
        device="cpu",
        inputs={},
    )


# ---------------------------------------------------------------------------
# diffusion mask resolution
# ---------------------------------------------------------------------------


def test_resolve_inpaint_mask_requires_connected_mask(ctx: RunContext):
    with pytest.raises(NodeExecutionError, match="mask"):
        resolve_inpaint_mask("powerpaint", _rgb(), ctx)


def test_resolve_inpaint_mask_uses_ctx_inputs(ctx: RunContext):
    ctx.inputs = {"mask": _mask(value=0.8)}
    out = resolve_inpaint_mask("flux_fill", _rgb(), ctx)
    assert out.shape == (16, 16)
    assert np.allclose(out, 0.8)


def test_resolve_inpaint_mask_rejects_shape_mismatch(ctx: RunContext):
    ctx.inputs = {"mask": _mask(8, 8)}
    with pytest.raises(NodeExecutionError, match="same image"):
        resolve_inpaint_mask("powerpaint", _rgb(16, 16), ctx)


def test_resolve_inpaint_mask_rejects_all_zero_when_required(ctx: RunContext):
    ctx.inputs = {"mask": _mask(value=0.0)}
    with pytest.raises(NodeExecutionError, match="empty"):
        resolve_inpaint_mask("powerpaint", _rgb(), ctx, require_nonzero=True)


# ---------------------------------------------------------------------------
# load_mask node
# ---------------------------------------------------------------------------


async def test_load_mask_from_asset_id(ctx: RunContext, tmp_path: Path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    asset_id = "abc123"
    Image.fromarray(np.full((16, 16), 200, dtype=np.uint8)).save(masks_dir / f"{asset_id}.png")
    ctx.weights_dir = tmp_path  # unused; node reads masks_dir from params or data root
    node = LoadMaskNode()
    # Pass masks root via params path convention used by the node
    out = await node.run(
        _rgb(),
        {"mask_id": asset_id, "masks_dir": str(masks_dir)},
        ctx,
    )
    assert out.shape == (16, 16, 3)
    assert float(out.mean()) == pytest.approx(200 / 255, abs=0.02)


async def test_load_mask_from_input_luma(ctx: RunContext):
    image = _rgb(value=0.25)
    out = await LoadMaskNode().run(image, {"source": "input"}, ctx)
    assert out.shape == (16, 16, 3)
    assert float(out.mean()) == pytest.approx(0.25, abs=0.02)


async def test_load_mask_missing_asset_explains(ctx: RunContext, tmp_path: Path):
    with pytest.raises(NodeExecutionError, match="mask_id"):
        await LoadMaskNode().run(
            _rgb(),
            {"mask_id": "missing", "masks_dir": str(tmp_path / "masks")},
            ctx,
        )


# ---------------------------------------------------------------------------
# mask-weighted blend
# ---------------------------------------------------------------------------


async def test_blend_mask_weighted(ctx: RunContext):
    a, b = _rgb(value=0.0), _rgb(value=1.0)
    # Left half masked → should pull toward b there when alpha=1
    mask = np.zeros((16, 16, 3), dtype=np.float32)
    mask[:, :8] = 1.0
    ctx.inputs = {"image": a, "image_b": b, "mask": mask}
    out = await BlendNode().run(a, {"alpha": 1.0, "mode": "normal"}, ctx)
    assert np.allclose(out[:, :8], 1.0)
    assert np.allclose(out[:, 8:], 0.0)


async def test_blend_without_mask_still_uniform(ctx: RunContext):
    a, b = _rgb(value=0.0), _rgb(value=1.0)
    ctx.inputs = {"image": a, "image_b": b}
    out = await BlendNode().run(a, {"alpha": 0.5, "mode": "normal"}, ctx)
    assert np.allclose(out, 0.5)


# ---------------------------------------------------------------------------
# mask asset API
# ---------------------------------------------------------------------------


@pytest.fixture
def services(data_dir: Path) -> AppServices:
    app_services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    for cls in ALL_FAKE_NODES:
        app_services.registry.register(cls)
    return app_services


@pytest.fixture
def client(services: AppServices):
    with TestClient(create_app(services)) as test_client:
        yield test_client


def _png_bytes(width: int = 32, height: int = 24, gray: int | None = None) -> bytes:
    if gray is not None:
        arr = np.full((height, width), gray, dtype=np.uint8)
        img = Image.fromarray(arr, mode="L")
    else:
        rng = np.random.default_rng(0)
        arr = (rng.random((height, width, 3)) * 255).astype(np.uint8)
        img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_mask_upload_and_fetch(client: TestClient):
    resp = client.post(
        "/api/masks",
        files={"mask": ("m.png", _png_bytes(gray=180), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    fetched = client.get(f"/api/masks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/")


def test_mask_scratch_returns_png(client: TestClient):
    resp = client.post(
        "/api/masks/scratch",
        files={"image": ("in.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
    img = Image.open(io.BytesIO(resp.content))
    assert img.mode in ("L", "RGB", "RGBA")


def test_load_mask_node_registered():
    from restoration.nodes import BUILTIN_NODES

    assert any(cls.id == "load_mask" for cls in BUILTIN_NODES)
