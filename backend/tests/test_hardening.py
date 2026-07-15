"""Backend-hardening: variant weights, ensembles, jobs, downloads, licence gates."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from restoration.api.app import create_app
from restoration.api.jobs import Job, JobManager, JobState
from restoration.core.analyzer import DegradationProfile
from restoration.core.ensemble import build_guided_ensemble
from restoration.core.errors import JobCancelled, PipelineValidationError
from restoration.core.executor import NodeSpec, PipelineSpec
from restoration.core.registry import NodeRegistry
from restoration.core.types import (
    BaseRestorationNode,
    LicenseInfo,
    LicenseKind,
    VramTier,
    WeightFile,
)
from restoration.core.weights import WeightManager
from restoration.nodes.ddcolor import DdColorNode
from restoration.nodes.realesrgan import RealEsrganNode
from restoration.nodes.scunet import ScunetNode
from restoration.nodes.swinir import SwinIrSrNode
from restoration.service import AppServices

from .conftest import ALL_FAKE_NODES
from .test_api import upload
from .test_weights import PAYLOAD, _manager, _url_weight

# ---------------------------------------------------------------------------
# Variant-aware weights
# ---------------------------------------------------------------------------

def test_variant_nodes_only_require_selected_checkpoint():
    dd = DdColorNode()
    assert [w.filename for w in dd.required_weight_files({"variant": "artistic"})] == [
        "ddcolor_artistic.pth"
    ]
    assert [w.filename for w in RealEsrganNode().required_weight_files({"scale": 2})] == [
        "RealESRGAN_x2plus.pth"
    ]
    assert [w.filename for w in ScunetNode().required_weight_files({"variant": "psnr"})] == [
        "scunet_color_real_psnr.pth"
    ]
    assert [w.filename for w in SwinIrSrNode().required_weight_files({"scale": 2})] == [
        "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_GAN.pth"
    ]


def test_is_installed_accepts_one_variant(tmp_path: Path):
    manager = WeightManager(tmp_path)
    node = DdColorNode()
    art = next(w for w in node.weight_manifest if w.filename == "ddcolor_artistic.pth")
    dest = manager.file_path(node.id, art)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"stub")

    assert manager.is_installed(node, {"variant": "artistic"}) is True
    assert manager.is_installed(node, {"variant": "modelscope"}) is False
    # Defaults (modelscope) not installed → overall installed false
    assert manager.is_installed(node) is False

    default = next(w for w in node.weight_manifest if w.filename == "ddcolor_modelscope.pth")
    manager.file_path(node.id, default).write_bytes(b"stub")
    assert manager.is_installed(node) is True
    status = manager.status(node)
    assert status.total_size_bytes == default.size_bytes
    assert status.missing_size_bytes == 0


def test_download_fetches_only_required_variant(tmp_path: Path):
    manager = _manager(tmp_path)

    class Dual(BaseRestorationNode):
        id = "dual"
        display_name = "Dual"
        vram_tier = VramTier.LOW
        license = LicenseInfo(
            spdx_id="Apache-2.0", kind=LicenseKind.PERMISSIVE, source_url="https://x"
        )
        weight_manifest = [
            WeightFile(
                filename="a.bin",
                size_bytes=len(PAYLOAD),
                sha256=None,
                url="https://example.invalid/a.bin",
            ),
            WeightFile(
                filename="b.bin",
                size_bytes=len(PAYLOAD),
                sha256=None,
                url="https://example.invalid/b.bin",
            ),
        ]
        param_schema = {
            "type": "object",
            "properties": {
                "which": {"type": "string", "enum": ["a", "b"], "default": "a"},
            },
        }

        def required_weight_files(self, params=None):
            which = (params or self.default_params()).get("which", "a")
            name = "a.bin" if which == "a" else "b.bin"
            return [w for w in self.weight_manifest if w.filename == name]

    node = Dual()
    manager.download(node, params={"which": "b"})
    assert manager.file_path(node.id, node.weight_manifest[1]).exists()
    assert not manager.file_path(node.id, node.weight_manifest[0]).exists()


def test_download_cancel_via_check_cancel(tmp_path: Path):
    manager = _manager(tmp_path)
    fires = {"n": 0}

    def check():
        fires["n"] += 1
        if fires["n"] >= 1:
            raise JobCancelled("stop")

    node_cls = type(
        "UnderTest",
        (BaseRestorationNode,),
        {
            "id": "under_test",
            "display_name": "Under test",
            "vram_tier": VramTier.LOW,
            "license": LicenseInfo(
                spdx_id="Apache-2.0",
                kind=LicenseKind.PERMISSIVE,
                source_url="https://example.invalid/LICENSE",
            ),
            "weight_manifest": [_url_weight()],
        },
    )
    with pytest.raises(JobCancelled):
        manager.download(node_cls(), check_cancel=check)
    assert manager.cleanup_partials("under_test") >= 0


def test_cleanup_partials(tmp_path: Path):
    manager = WeightManager(tmp_path)
    part = manager.node_dir("under_test") / "model.bin.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"partial")
    assert manager.cleanup_partials("under_test") == 1
    assert not part.exists()


# ---------------------------------------------------------------------------
# Ensemble + highlight profile
# ---------------------------------------------------------------------------

def test_invalid_ensemble_mode_raises():
    reg = NodeRegistry()
    reg.register_builtins()
    with pytest.raises(PipelineValidationError, match="invalid ensemble mode"):
        build_guided_ensemble(None, registry=reg, mode="not_a_mode")


def test_ensemble_accepts_profile_dict_via_service(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    profile = DegradationProfile(
        width=64,
        height=64,
        blur_score=200,
        noise_score=0.001,
        jpeg_blockiness=0.0,
        mean_luma=0.9,
        dark_fraction=0.0,
        bright_fraction=0.4,
        face_count=0,
        low_light=False,
        blown_highlights=True,
        clip_fraction=0.08,
        over_exposure=0.7,
    )
    plan = services.build_ensemble(
        prompt_preset_id="blown_highlight_rescue",
        mode="guide_and_finish",
        profile=profile,
    )
    assert plan["instruction"]
    assert "pipeline" in plan


def test_profile_roundtrip():
    profile = DegradationProfile(
        width=10,
        height=20,
        blur_score=1.0,
        noise_score=0.01,
        jpeg_blockiness=0.1,
        mean_luma=0.5,
        dark_fraction=0.1,
        bright_fraction=0.1,
        face_count=2,
        low_light=True,
        blown_highlights=False,
        is_grayscale=True,
        confidence={"noise": 0.9},
    )
    restored = DegradationProfile.from_dict(profile.to_dict())
    assert restored.width == 10
    assert restored.is_grayscale is True
    assert restored.face_count == 2


# ---------------------------------------------------------------------------
# Job retention
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_ttl_and_delete(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    for cls in ALL_FAKE_NODES:
        services.registry.register(cls)
    jobs = JobManager(services, root=data_dir / "jobs", max_jobs=3, ttl_seconds=1)
    await jobs.start()
    try:
        img = np.zeros((8, 8, 3), dtype=np.float32)
        spec = PipelineSpec(nodes=[NodeSpec(id="a", type="recording")], edges=[])
        j1 = await jobs.submit(spec, img)
        j1.state = JobState.DONE
        j1.finished_at = time.time() - 10
        (jobs.root / j1.id).mkdir(parents=True, exist_ok=True)
        (jobs.root / j1.id / "result.png").write_bytes(b"x")

        purged = jobs.cleanup()
        assert j1.id in purged
        assert jobs.get(j1.id) is None
        assert not (jobs.root / j1.id).exists()

        j2 = await jobs.submit(spec, img)
        j2.state = JobState.DONE
        j2.finished_at = time.time()
        assert jobs.delete(j2.id) is True
        assert jobs.get(j2.id) is None
    finally:
        await jobs.stop()


def test_events_truncated_flag(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    jobs = JobManager(services, root=data_dir / "jobs")
    img = np.zeros((4, 4, 3), dtype=np.float32)
    spec = PipelineSpec(nodes=[NodeSpec(id="a", type="recording")], edges=[])
    job = Job(id="trunc", spec=spec, image=img)
    jobs._jobs[job.id] = job
    for i in range(2100):
        jobs._publish(job, {"i": i, "status": "running", "node_id": "a", "progress": 0})
    assert job.events_truncated is True
    assert len(job.events) == 2000
    assert job.to_dict()["events_truncated"] is True


# ---------------------------------------------------------------------------
# Licence gates on presets / API
# ---------------------------------------------------------------------------

@pytest.fixture
def client(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    for cls in ALL_FAKE_NODES:
        services.registry.register(cls)
    with TestClient(create_app(services)) as test_client:
        yield test_client, services


def test_preset_list_includes_licence_gate(client):
    test_client, _services = client
    pipeline = {
        "version": 1,
        "nodes": [{"id": "a", "type": "gated", "params": {}, "pinned": False}],
        "edges": [],
    }
    saved = test_client.put(
        "/api/presets/gated-run", json={"pipeline": pipeline, "description": "g"}
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["licence"]["ready"] is False
    assert "gated" in body["licence"]["unacknowledged_node_ids"]

    listed = test_client.get("/api/presets").json()
    assert any(p["name"] == "gated-run" for p in listed)
    filtered = test_client.get("/api/presets", params={"include_gated": False}).json()
    assert not any(p["name"] == "gated-run" for p in filtered)


def test_running_gated_preset_without_ack_is_403(client):
    test_client, services = client
    # Install fake gated weights so the failure is licence, not missing weights.
    node = services.registry.create("gated")
    for wf in node.weight_manifest:
        path = services.weights.file_path(node.id, wf)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    pipeline = {
        "version": 1,
        "nodes": [{"id": "a", "type": "gated", "params": {}, "pinned": False}],
        "edges": [],
    }
    test_client.put("/api/presets/gated-run", json={"pipeline": pipeline})
    resp = test_client.post("/api/jobs", **upload(data={"preset": "gated-run"}))
    assert resp.status_code == 403
    assert resp.json()["error"] == "LicenseNotAcknowledgedError"


def test_ensemble_api_invalid_mode(client):
    test_client, _ = client
    resp = test_client.post(
        "/api/pipelines/ensemble",
        json={"mode": "nope", "prompt_preset_id": "instruct_only_general"},
    )
    assert resp.status_code == 400


def test_ensemble_api_ok(client):
    test_client, _ = client
    resp = test_client.post(
        "/api/pipelines/ensemble",
        json={"mode": "instruct_only", "prompt_preset_id": "instruct_only_general"},
    )
    assert resp.status_code == 200
    assert resp.json()["chain"] == ["instructir"]


def test_missing_weights_is_variant_aware(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    node = RealEsrganNode()
    x2 = next(w for w in node.weight_manifest if "x2" in w.filename)
    dest = services.weights.file_path(node.id, x2)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"stub")

    spec = PipelineSpec(
        nodes=[NodeSpec(id="u", type="realesrgan", params={"scale": 2})],
        edges=[],
    )
    assert services.missing_weights(spec) == []

    spec4 = PipelineSpec(
        nodes=[NodeSpec(id="u", type="realesrgan", params={"scale": 4})],
        edges=[],
    )
    assert services.missing_weights(spec4) == ["realesrgan"]


def test_instructir_declares_text_encoder_weights():
    from restoration.nodes.instructir import InstructIrNode

    names = {w.filename for w in InstructIrNode.weight_manifest}
    assert "im_instructir-7d.pt" in names
    assert "bge-micro-v2/model.safetensors" in names
    assert "bge-micro-v2/tokenizer.json" in names


# ---------------------------------------------------------------------------
# v0.6 API contracts + overlays + cleanup
# ---------------------------------------------------------------------------

def test_health_reports_v060_and_api_version(client):
    test_client, _ = client
    body = test_client.get("/api/health").json()
    assert body["version"] == "0.6.0"
    assert body["api_version"] == "1.0.0"


def test_instructir_prompts_api(client):
    test_client, _ = client
    body = test_client.get("/api/instructir/prompts").json()
    assert body["count"] >= 16
    assert len(body["presets"]) == body["count"]
    assert any(p["id"] == "blown_highlight_rescue" for p in body["presets"])


def test_job_delete_and_cleanup_endpoints(client):
    test_client, _ = client
    pipeline = '{"version":1,"nodes":[{"id":"a","type":"recording"}],"edges":[]}'
    job_id = test_client.post("/api/jobs", **upload(data={"pipeline": pipeline})).json()["id"]
    # Wait until done so delete is allowed on a finished job.
    for _ in range(200):
        state = test_client.get(f"/api/jobs/{job_id}").json()["state"]
        if state in ("done", "error", "cancelled"):
            break
        time.sleep(0.02)
    assert test_client.delete(f"/api/jobs/{job_id}").json()["deleted"] is True
    assert test_client.get(f"/api/jobs/{job_id}").status_code == 404
    cleaned = test_client.post("/api/jobs/cleanup").json()
    assert "purged" in cleaned and "remaining" in cleaned


def test_download_cancel_endpoint(client, monkeypatch):
    """Cancel mid-download clears progress and reports cancelled state."""
    test_client, services = client
    barrier = {"started": False}

    def slow_download(node, on_progress=None, **kwargs):
        barrier["started"] = True
        for i in range(50):
            check = kwargs.get("check_cancel")
            if check:
                check()
            if on_progress:
                on_progress("model.bin", i, 50)
            time.sleep(0.02)

    monkeypatch.setattr(services.weights, "download", slow_download)
    resp = test_client.post("/api/weights/needs_weights/download")
    assert resp.status_code == 202
    download_id = resp.json()["id"]
    for _ in range(100):
        if barrier["started"]:
            break
        time.sleep(0.01)
    cancel = test_client.post(f"/api/weights/downloads/{download_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["cancelled"] is True
    state = "running"
    for _ in range(200):
        state = test_client.get(f"/api/weights/downloads/{download_id}").json()["state"]
        if state in ("cancelled", "done", "error"):
            break
        time.sleep(0.02)
    assert state == "cancelled"


def test_grayscale_routes_to_ddcolor():
    from restoration.core.rules import RuleTable

    table = RuleTable.load_default()
    decision = table.route(
        DegradationProfile(
            width=1200,
            height=900,
            blur_score=500.0,
            noise_score=0.001,
            jpeg_blockiness=0.0,
            mean_luma=0.5,
            dark_fraction=0.0,
            bright_fraction=0.0,
            face_count=0,
            low_light=False,
            blown_highlights=False,
            is_grayscale=True,
        )
    )
    assert "ddcolor" in decision.chain
    assert decision.params["ddcolor"]["variant"] == "modelscope"


def test_companion_overlay_instructir_when_ready(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    services.registry.register_builtins()
    node = services.registry.create("instructir")
    for wf in node.weight_manifest:
        path = services.weights.file_path(node.id, wf)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stub")
    if node.license.requires_acknowledgement:
        services.weights.acknowledge_license(node)

    profile = DegradationProfile(
        width=128,
        height=128,
        blur_score=200,
        noise_score=0.001,
        jpeg_blockiness=0.0,
        mean_luma=0.9,
        dark_fraction=0.0,
        bright_fraction=0.5,
        face_count=0,
        low_light=False,
        blown_highlights=True,
        clip_fraction=0.08,
        over_exposure=0.7,
    )
    chain, params, reasons = services._apply_companion_overlays(profile, ["realesrgan"], {})
    assert "instructir" in chain
    assert params["instructir"].get("mask_highlights") is True
    assert any(r["node"] == "instructir" for r in reasons)


def test_companion_overlay_skipped_when_not_installed(data_dir: Path):
    services = AppServices(data_dir=data_dir, force_cpu=True, seed_builtin_presets=False)
    services.registry.register_builtins()
    profile = DegradationProfile(
        width=128,
        height=128,
        blur_score=200,
        noise_score=0.001,
        jpeg_blockiness=0.0,
        mean_luma=0.9,
        dark_fraction=0.0,
        bright_fraction=0.5,
        face_count=0,
        low_light=False,
        blown_highlights=True,
        clip_fraction=0.08,
        over_exposure=0.7,
    )
    chain, _params, reasons = services._apply_companion_overlays(profile, ["realesrgan"], {})
    assert "instructir" not in chain
    assert not any(r["node"] == "instructir" for r in reasons)


def test_soft_blend_masked_alpha_channel_preserved():
    from restoration.core.highlight import soft_blend_masked

    original = np.zeros((16, 16, 4), dtype=np.float32)
    original[..., 3] = 0.75
    restored = np.ones((16, 16, 4), dtype=np.float32)
    mask = np.zeros((16, 16), dtype=np.float32)
    mask[4:12, 4:12] = 1.0
    out = soft_blend_masked(original, restored, mask, feather=0.0)
    assert out.shape == (16, 16, 4)
    assert float(out[0, 0, 3]) == 0.75
    assert float(out[8, 8, 0]) == 1.0
    assert float(out[0, 0, 0]) == 0.0


def test_instructir_invalid_mode_raises(tmp_path: Path):
    from restoration.core.types import RunContext
    from restoration.nodes.instructir import InstructIrNode

    node = InstructIrNode()
    ctx = RunContext(job_id="t", node_id="instructir", device="cpu", weights_dir=str(tmp_path))
    with pytest.raises(PipelineValidationError, match="invalid InstructIR mode"):
        node.run_sync(
            np.zeros((8, 8, 3), dtype=np.float32),
            {"mode": "not_a_real_mode", "instruction": "fix it"},
            ctx,
        )
