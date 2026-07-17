"""Phase 4: local VLM Auto describe/plan + skill routing."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from restoration.api.app import create_app
from restoration.core.auto_plan import load_skill_text, plan_from_description
from restoration.core.vlm import PhotoDescription, VlmManager, description_from_profile
from restoration.presets import Preset
from restoration.service import AppServices

from .conftest import ALL_FAKE_NODES


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


def png_bytes(width: int = 64, height: int = 48, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    array = (rng.random((height, width, 3)) * 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def test_skill_md_is_shipped():
    text = load_skill_text()
    assert "osdface" in text
    assert "rule_table" in text


def test_vlm_status_not_installed(client):
    body = client.get("/api/vlm").json()
    assert body["id"] == "vlm"
    assert body["installed"] is False
    assert "Qwen" in body["display_name"]
    assert body["size_bytes"] > 0


def test_describe_heuristic_fallback(client):
    resp = client.post(
        "/api/auto/describe",
        files={"image": ("in.png", png_bytes(), "image/png")},
        data={"force_heuristic": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"]["source"] == "heuristic"
    assert "width" in body["description"]
    assert body["vlm"]["installed"] is False


def test_auto_plan_skill_returns_pipeline(client):
    resp = client.post(
        "/api/auto/plan",
        files={"image": ("in.png", png_bytes(), "image/png")},
        data={"goal": "", "fallback": "skill", "force_heuristic": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["planner"] == "skill"
    assert body["pipeline"]["nodes"]
    assert "routing" in body
    assert "description" in body
    assert isinstance(body.get("suggestions"), list)


def test_auto_plan_rule_table_fallback(client):
    resp = client.post(
        "/api/auto/plan",
        files={"image": ("in.png", png_bytes(), "image/png")},
        data={"fallback": "rule_table"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["planner"] == "rule_table"
    assert body["pipeline"]["nodes"]


def test_auto_suggest_returns_suggestions_and_user_presets(client, services):
    services.presets.save(
        Preset(
            name="My Custom",
            description="user",
            pipeline={
                "version": 1,
                "nodes": [{"id": "a", "type": "recording", "params": {}}],
                "edges": [],
            },
        )
    )
    resp = client.post(
        "/api/auto/suggest",
        files={"image": ("in.png", png_bytes(), "image/png")},
        data={"force_heuristic": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "suggestions" in body
    assert any(p["name"] == "My Custom" for p in body["user_presets"])


def test_archival_goal_skips_colorize():
    desc = PhotoDescription(
        content_type="portrait",
        is_grayscale=True,
        is_bw_intended=True,
        has_faces=True,
        face_count=1,
        degradations=["jpeg"],
        width=800,
        height=600,
        summary="archival scan",
        source="heuristic",
        profile={"defect_score": 0.0, "low_light": False},
    )
    from restoration.core.registry import NodeRegistry

    registry = NodeRegistry()
    registry.register_builtins()
    plan = plan_from_description(desc, registry, goal="archival", installed=set())
    types = [n["type"] for n in plan.pipeline["nodes"]]
    assert "ddcolor" not in types


def test_description_from_profile_flags(services):
    rng = np.random.default_rng(1)
    image = (rng.random((64, 64, 3)) * 0.05).astype(np.float32)
    profile = services.analyzer.analyze(image)
    desc = description_from_profile(profile)
    assert desc.source == "heuristic"
    assert desc.width == 64


def test_vlm_manager_installed_detection(tmp_path: Path):
    mgr = VlmManager(tmp_path / "vlm")
    assert mgr.is_installed() is False
    model = mgr.model_dir
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf-8")
    (model / "model.safetensors").write_bytes(b"fake")
    assert mgr.is_installed() is True
    assert mgr.status()["installed"] is True


def test_vlm_download_endpoint_starts(client, monkeypatch, services):
    calls = {"n": 0}

    def fake_download(progress=None, check_cancel=None):
        calls["n"] += 1
        if progress:
            progress("snapshot", 10, 100)
            progress("snapshot", 100, 100)
        services.vlm.model_dir.mkdir(parents=True, exist_ok=True)
        (services.vlm.model_dir / "config.json").write_text("{}", encoding="utf-8")
        (services.vlm.model_dir / "model.safetensors").write_bytes(b"x")
        return services.vlm.model_dir

    monkeypatch.setattr(services.vlm, "download", fake_download)
    resp = client.post("/api/vlm/download")
    assert resp.status_code == 202
    state = resp.json()
    deadline = time.time() + 2
    while time.time() < deadline:
        state = client.get(f"/api/weights/downloads/{state['id']}").json()
        if state["state"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.05)
    assert state["state"] == "done"
    assert calls["n"] == 1
    assert client.get("/api/vlm").json()["installed"] is True


def test_describe_preset_marks_builtin(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=True)
    presets = [services.describe_preset(p) for p in services.presets.list()]
    builtins = [p for p in presets if p.get("builtin")]
    assert builtins
    assert all(isinstance(p["builtin"], bool) for p in presets)
