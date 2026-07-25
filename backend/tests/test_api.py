"""REST + WebSocket surface.

Uses fake nodes registered onto the real service, so the HTTP contract is tested
without a GPU or a checkpoint — the backend has to be exercisable with zero UI
and zero weights (ARCHITECTURE.md section 1).
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from restoration.api.app import create_app
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


def png_bytes(width: int = 32, height: int = 24, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    array = (rng.random((height, width, 3)) * 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(**extra):
    return {"files": {"image": ("in.png", png_bytes(), "image/png")}, **extra}


def wait_for_terminal(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["state"] in ("done", "error", "cancelled"):
            return payload
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached a terminal state")


CHAIN = '{"version": 1, "nodes": [{"id": "a", "type": "recording"}], "edges": []}'


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------

def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["plugin_errors"] == []


def test_hardware_reports_cpu_when_forced(client):
    body = client.get("/api/hardware").json()
    assert body["backend"] == "cpu"


def test_list_nodes_includes_availability_and_weight_state(client):
    nodes = client.get("/api/nodes").json()
    by_id = {n["id"]: n for n in nodes}

    assert "realesrgan" in by_id
    realesrgan = by_id["realesrgan"]
    assert realesrgan["license"]["spdx_id"] == "BSD-3-Clause"
    assert realesrgan["weights"]["installed"] is False
    assert realesrgan["availability"]["state"] in ("available", "unavailable")


def test_high_tier_nodes_are_greyed_with_a_reason_on_cpu(client):
    """Never hidden, always explained (ARCHITECTURE.md section 5)."""
    by_id = {n["id"]: n for n in client.get("/api/nodes").json()}
    fatal = by_id["oom_fatal"]
    assert fatal["availability"]["state"] == "unavailable"
    assert "GPU" in fatal["availability"]["reason"]


def test_get_unknown_node_is_a_400(client):
    assert client.get("/api/nodes/ghost").status_code == 400


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def test_analyze_returns_profile_routing_and_pipeline(client):
    body = client.post("/api/analyze", **upload()).json()
    assert body["profile"]["width"] == 32
    assert body["routing"]["chain"]
    assert body["pipeline"]["nodes"]
    # The real models aren't downloaded in tests, so the auto-pipeline reports
    # exactly what a first-run user would see. A 32px upload is well under the
    # 800px band, so the default routes to RealESRGAN.
    assert "realesrgan" in body["routing"]["chain"]
    assert "realesrgan" in body["missing_weights"]
    assert "swinir" not in body["routing"]["chain"]
    assert "diffbir" not in body["routing"]["chain"]
    assert "hat" not in body["routing"]["chain"]


def test_analyze_rejects_an_empty_upload(client):
    response = client.post("/api/analyze", files={"image": ("x.png", b"", "image/png")})
    assert response.status_code == 400


def test_analyze_draft_quality_keeps_realesrgan(client):
    """Draft no longer swaps away SwinIR (Legacy); small images already use RealESRGAN."""
    body = client.post("/api/analyze", **upload(data={"quality_tier": "draft"})).json()
    assert "realesrgan" in body["routing"]["chain"]
    assert "mambair" not in body["routing"]["chain"]
    assert "swinir" not in body["routing"]["chain"]


def test_analyze_rejects_an_unknown_quality_tier(client):
    response = client.post("/api/analyze", **upload(data={"quality_tier": "ultra"}))
    assert response.status_code == 400


def test_job_submission_honours_quality_tier_for_the_auto_pipeline(client):
    """The real nodes' weights aren't installed in tests, so this 409s before a
    job is created — that's fine, the point is confirming the quality-tier
    path already resolved against the active stack."""
    response = client.post("/api/jobs", **upload(data={"quality_tier": "draft"}))
    assert response.status_code == 409
    assert "swinir" not in response.json()["detail"]
    assert "realesrgan" in response.json()["detail"]


def test_analyze_rejects_a_non_image(client):
    response = client.post("/api/analyze", files={"image": ("x.png", b"nope", "image/png")})
    assert response.status_code == 400
    assert "unreadable image" in response.json()["detail"]


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def test_submit_run_and_fetch_the_result(client):
    submitted = client.post("/api/jobs", **upload(data={"pipeline": CHAIN}))
    assert submitted.status_code == 202
    job_id = submitted.json()["id"]

    final = wait_for_terminal(client, job_id)
    assert final["state"] == "done"
    assert final["result_url"] == f"/api/jobs/{job_id}/result"

    result = client.get(final["result_url"])
    assert result.status_code == 200
    assert result.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(result.content)).size == (32, 24)


def test_auto_pipeline_is_used_when_no_pipeline_is_given(client, services):
    """Simple Mode's whole request: an image, and nothing else."""
    # The fake analyzer chain would need real weights, so route to a fake node.
    services.rule_table.stages = []
    services.rule_table.fallback_chain = ["recording"]

    submitted = client.post("/api/jobs", **upload())
    assert submitted.status_code == 202
    body = submitted.json()
    assert body["analysis"]["routing"]["chain"] == ["recording"]

    assert wait_for_terminal(client, body["id"])["state"] == "done"


def test_job_with_missing_weights_is_a_409(client):
    pipeline = '{"version": 1, "nodes": [{"id": "a", "type": "needs_weights"}], "edges": []}'
    response = client.post("/api/jobs", **upload(data={"pipeline": pipeline}))
    assert response.status_code == 409
    assert "not installed" in response.json()["detail"]


def test_invalid_pipeline_json_is_a_400(client):
    response = client.post("/api/jobs", **upload(data={"pipeline": "{not json"}))
    assert response.status_code == 400


def test_pipeline_with_unknown_node_is_a_400(client):
    pipeline = '{"version": 1, "nodes": [{"id": "a", "type": "ghost"}], "edges": []}'
    response = client.post("/api/jobs", **upload(data={"pipeline": pipeline}))
    assert response.status_code == 400
    assert "unknown node type" in response.json()["detail"]


def test_pipeline_and_preset_together_is_a_400(client):
    response = client.post("/api/jobs", **upload(data={"pipeline": CHAIN, "preset": "x"}))
    assert response.status_code == 400


def test_failing_node_marks_the_job_errored_not_the_app(client):
    pipeline = '{"version": 1, "nodes": [{"id": "a", "type": "boom"}], "edges": []}'
    job_id = client.post("/api/jobs", **upload(data={"pipeline": pipeline})).json()["id"]

    final = wait_for_terminal(client, job_id)
    assert final["state"] == "error"
    assert "node exploded" in final["error"]

    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409


def test_cancel_a_running_job(client):
    pipeline = '{"version": 1, "nodes": [{"id": "a", "type": "slow"}], "edges": []}'
    job_id = client.post("/api/jobs", **upload(data={"pipeline": pipeline})).json()["id"]

    assert client.post(f"/api/jobs/{job_id}/cancel").json()["cancelled"] is True
    assert wait_for_terminal(client, job_id)["state"] == "cancelled"

    # A finished job cannot be cancelled again.
    assert client.post(f"/api/jobs/{job_id}/cancel").json()["cancelled"] is False


def test_unknown_job_is_a_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_jobs_are_listed_newest_first(client):
    first = client.post("/api/jobs", **upload(data={"pipeline": CHAIN})).json()["id"]
    wait_for_terminal(client, first)
    second = client.post("/api/jobs", **upload(data={"pipeline": CHAIN})).json()["id"]
    wait_for_terminal(client, second)

    listed = [j["id"] for j in client.get("/api/jobs").json()]
    assert listed[:2] == [second, first]


# ---------------------------------------------------------------------------
# websocket progress
# ---------------------------------------------------------------------------

def test_websocket_streams_progress_to_a_terminal_event(client):
    job_id = client.post("/api/jobs", **upload(data={"pipeline": CHAIN})).json()["id"]

    events = []
    with client.websocket_connect(f"/api/jobs/{job_id}/events") as websocket:
        while True:
            try:
                events.append(websocket.receive_json())
            except Exception:
                break

    assert events, "expected at least one progress event"
    statuses = {(e["node_id"], e["status"]) for e in events}
    assert ("a", "queued") in statuses
    assert ("a", "done") in statuses
    # node_id "" is the job-level terminal event.
    assert ("", "done") in statuses


def test_websocket_for_an_unknown_job_is_closed(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/jobs/ghost/events") as websocket:
            websocket.receive_json()
    assert excinfo.value.code == 4004


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------

def test_list_weights(client, services):
    body = client.get("/api/weights").json()
    assert body["cache_dir"].endswith("weights")
    node_ids = {n["node_id"] for n in body["nodes"]}
    assert {"realesrgan", "gfpgan", "lama"} <= node_ids
    assert "blend" not in node_ids  # no manifest, so nothing to manage


def test_acknowledge_a_gated_licence(client):
    body = client.post("/api/weights/gated/acknowledge", json={"accepted": True}).json()
    assert body["acknowledged"] is True

    refused = client.post("/api/weights/gated/acknowledge", json={"accepted": False})
    assert refused.status_code == 400


def test_download_without_acknowledgement_is_a_403(client):
    response = client.post("/api/weights/gated/download")
    assert response.status_code == 403
    assert response.json()["error"] == "LicenseNotAcknowledgedError"


def test_download_status_for_unknown_id_is_404(client):
    assert client.get("/api/weights/downloads/nope").status_code == 404


def test_remove_weights(client):
    assert client.delete("/api/weights/realesrgan").json() == {"removed": False}
    assert client.delete("/api/weights/ghost").status_code == 400


# ---------------------------------------------------------------------------
# presets
# ---------------------------------------------------------------------------

def test_preset_crud(client):
    pipeline = {"version": 1, "nodes": [{"id": "a", "type": "recording"}], "edges": []}

    body = {"pipeline": pipeline, "description": "d"}
    saved = client.put("/api/presets/my-preset", json=body)
    assert saved.status_code == 200
    assert saved.json()["name"] == "my-preset"

    assert [p["name"] for p in client.get("/api/presets").json()] == ["my-preset"]
    assert client.get("/api/presets/my-preset").json()["description"] == "d"

    assert client.delete("/api/presets/my-preset").json() == {"deleted": True}
    assert client.get("/api/presets").json() == []


def test_saving_an_unexecutable_preset_is_rejected_at_save_time(client):
    bad = {"version": 1, "nodes": [{"id": "a", "type": "ghost"}], "edges": []}
    response = client.put("/api/presets/bad", json={"pipeline": bad})
    assert response.status_code == 400
    assert client.get("/api/presets").json() == []


def test_running_a_saved_preset(client):
    pipeline = {"version": 1, "nodes": [{"id": "a", "type": "recording"}], "edges": []}
    client.put("/api/presets/chain", json={"pipeline": pipeline})

    job_id = client.post("/api/jobs", **upload(data={"preset": "chain"})).json()["id"]
    assert wait_for_terminal(client, job_id)["state"] == "done"


def test_unknown_preset_is_a_400(client):
    assert client.get("/api/presets/ghost").status_code == 400


# ---------------------------------------------------------------------------
# pipeline building: auto-order + .txt workflows (Advanced pipeline builder)
# ---------------------------------------------------------------------------

def test_auto_order_arranges_a_scrambled_selection(client):
    body = client.post(
        "/api/pipelines/auto-order",
        json={"node_types": ["restoreformer", "fbcnn", "gfpgan"]},
    ).json()
    assert [n["type"] for n in body["nodes"]] == ["fbcnn", "restoreformer", "gfpgan"]


def test_auto_order_rejects_an_unknown_node_type(client):
    resp = client.post("/api/pipelines/auto-order", json={"node_types": ["ghost"]})
    assert resp.status_code == 400


def test_workflow_export_then_import_round_trips(client):
    pipeline = {"version": 1, "nodes": [{"id": "a", "type": "recording"}], "edges": []}
    exported = client.post(
        "/api/workflows/export",
        json={"pipeline": pipeline, "name": "my workflow", "description": "test"},
    ).json()
    text = exported["text"]
    assert text.startswith("# Restoration Workflow")
    assert "my workflow" in text

    # Round-trips through the same parse_pipeline() validator as everything
    # else, which fills in the normalized defaults (params, pinned) the
    # original hand-written pipeline omitted.
    imported = client.post("/api/workflows/import", json={"text": text}).json()
    assert imported["nodes"] == [
        {"id": "a", "type": "recording", "params": {}, "pinned": False}
    ]
    assert imported["edges"] == []


def test_workflow_import_rejects_a_body_with_no_json(client):
    resp = client.post("/api/workflows/import", json={"text": "# just a header\n"})
    assert resp.status_code == 400


def test_workflow_import_rejects_malformed_json(client):
    resp = client.post("/api/workflows/import", json={"text": "# header\n{not json"})
    assert resp.status_code == 400
