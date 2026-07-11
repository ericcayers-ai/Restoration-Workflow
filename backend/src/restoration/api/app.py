"""FastAPI backend: REST + one WebSocket per job.

Bound to localhost by the CLI (``restore serve``), never to a public interface.
The frontend is one client of this API and not a privileged one — the same
surface drives the CLI, a curl session and any automation script, which is what
makes the engine testable with no UI running at all (ARCHITECTURE.md section 1).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import API_VERSION, __version__
from ..core.errors import (
    ChecksumMismatchError,
    InferenceUnavailableError,
    InsufficientDiskSpaceError,
    LicenseNotAcknowledgedError,
    NodeExecutionError,
    OutOfMemoryError,
    PipelineValidationError,
    PluginError,
    RestorationError,
    WeightsNotInstalledError,
)
from ..core.executor import parse_pipeline
from ..core.images import load_image_bytes
from ..presets import Preset, PresetStore
from ..service import AppServices
from .frontend import mount_frontend
from .jobs import JobManager
from .weights import DownloadManager

# Typed engine errors map onto HTTP status; nothing leaks as a bare 500 that we
# have a better answer for.
_STATUS_FOR: list[tuple[type[RestorationError], int]] = [
    (LicenseNotAcknowledgedError, 403),
    (InsufficientDiskSpaceError, 507),
    (ChecksumMismatchError, 502),
    (WeightsNotInstalledError, 409),
    (InferenceUnavailableError, 503),
    (OutOfMemoryError, 507),
    (PipelineValidationError, 400),
    (PluginError, 500),
    (NodeExecutionError, 500),
]


def _status_for(exc: RestorationError) -> int:
    for kind, status in _STATUS_FOR:
        if isinstance(exc, kind):
            return status
    return 500


class PresetBody(BaseModel):
    pipeline: dict[str, Any]
    description: str = ""


class AcknowledgeBody(BaseModel):
    accepted: bool = Field(..., description="Must be true; the user's explicit attestation.")


def create_app(services: AppServices | None = None) -> FastAPI:
    services = services or AppServices()
    jobs = JobManager(services)
    downloads = DownloadManager(services)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await jobs.start()
        try:
            yield
        finally:
            await jobs.stop()

    app = FastAPI(
        title="Restoration Workflow",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.services = services
    app.state.jobs = jobs
    app.state.downloads = downloads

    @app.exception_handler(RestorationError)
    async def _engine_error(_request: Request, exc: RestorationError) -> JSONResponse:
        return JSONResponse(
            status_code=_status_for(exc),
            content={
                "error": type(exc).__name__,
                "detail": str(exc),
                "fallback": getattr(exc, "fallback", None),
            },
        )

    # -- meta ---------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "api_version": API_VERSION,
            "plugin_errors": services.registry.plugin_errors,
        }

    @app.get("/api/hardware")
    async def hardware() -> dict[str, Any]:
        return services.hardware.detect().to_dict()

    # -- nodes ---------------------------------------------------------------

    @app.get("/api/nodes")
    async def list_nodes() -> list[dict[str, Any]]:
        return services.describe_nodes()

    @app.get("/api/nodes/{node_id}")
    async def get_node(node_id: str) -> dict[str, Any]:
        return services.describe_node(node_id)

    # -- analysis ------------------------------------------------------------

    async def _read_image(upload: UploadFile) -> Any:
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty image upload")
        try:
            return load_image_bytes(data)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"unreadable image: {exc}") from exc

    @app.post("/api/analyze")
    async def analyze(image: UploadFile = File(...)) -> dict[str, Any]:
        array = await _read_image(image)
        auto = await asyncio.to_thread(services.analyze, array)
        payload = auto.to_dict()
        payload["missing_weights"] = services.missing_weights(auto.spec)
        return payload

    # -- jobs ----------------------------------------------------------------

    @app.post("/api/jobs", status_code=202)
    async def submit_job(
        image: UploadFile = File(...),
        pipeline: str | None = Form(None),
        preset: str | None = Form(None),
    ) -> dict[str, Any]:
        """Submit a pipeline. With neither ``pipeline`` nor ``preset``, the
        degradation analyzer picks one — that is Simple Mode's entire request."""
        array = await _read_image(image)

        analysis: dict[str, Any] | None = None
        if pipeline and preset:
            raise HTTPException(400, "pass either 'pipeline' or 'preset', not both")

        if pipeline:
            try:
                document = json.loads(pipeline)
            except json.JSONDecodeError as exc:
                raise HTTPException(400, f"'pipeline' is not valid JSON: {exc}") from exc
            spec = parse_pipeline(document, services.registry)
        elif preset:
            spec = parse_pipeline(services.presets.get(preset).pipeline, services.registry)
        else:
            auto = await asyncio.to_thread(services.analyze, array)
            spec = auto.spec
            analysis = auto.to_dict()

        missing = services.missing_weights(spec)
        if missing:
            raise WeightsNotInstalledError(", ".join(missing))

        job = await jobs.submit(spec, array, analysis=analysis)
        return job.to_dict()

    @app.get("/api/jobs")
    async def list_jobs() -> list[dict[str, Any]]:
        return [job.to_dict() for job in jobs.list()]

    def _job_or_404(job_id: str) -> Any:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id!r}")
        return job

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        return _job_or_404(job_id).to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, Any]:
        job = _job_or_404(job_id)
        return {"cancelled": jobs.cancel(job_id), "state": job.state.value}

    @app.get("/api/jobs/{job_id}/result")
    async def job_result(job_id: str) -> FileResponse:
        job = _job_or_404(job_id)
        if job.result_path is None or not job.result_path.exists():
            raise HTTPException(409, f"job {job_id} has no result (state: {job.state.value})")
        return FileResponse(job.result_path, media_type="image/png")

    @app.get("/api/jobs/{job_id}/previews/{index}")
    async def job_preview(job_id: str, index: int) -> FileResponse:
        job = _job_or_404(job_id)
        path = jobs.root / job.id / f"preview_{index}.png"
        if not path.exists():
            raise HTTPException(404, "no such preview")
        return FileResponse(path, media_type="image/png")

    @app.websocket("/api/jobs/{job_id}/events")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        if jobs.get(job_id) is None:
            await websocket.close(code=4004, reason="no such job")
            return
        try:
            async for event in jobs.subscribe(job_id):
                await websocket.send_json(event)
        except WebSocketDisconnect:  # pragma: no cover - client went away
            return
        finally:
            try:
                await websocket.close()
            except RuntimeError:  # pragma: no cover - already closed
                pass

    # -- weights -------------------------------------------------------------

    @app.get("/api/weights")
    async def list_weights() -> dict[str, Any]:
        return {
            "cache_dir": str(services.weights.root),
            "nodes": [
                services.weights.status(node).to_dict()
                for node in services.registry.all_nodes()
                if node.weight_manifest
            ],
            "installed": services.weights.list_installed(),
        }

    @app.post("/api/weights/{node_id}/acknowledge")
    async def acknowledge(node_id: str, body: AcknowledgeBody) -> dict[str, Any]:
        if not body.accepted:
            raise HTTPException(400, "acknowledgement requires accepted=true")
        node = services.registry.create(node_id)
        services.weights.acknowledge_license(node)
        return services.weights.status(node).to_dict()

    @app.post("/api/weights/{node_id}/download", status_code=202)
    async def download_weights(node_id: str) -> dict[str, Any]:
        return downloads.start(node_id).to_dict()

    @app.get("/api/weights/downloads/{download_id}")
    async def download_status(download_id: str) -> dict[str, Any]:
        state = downloads.get(download_id)
        if state is None:
            raise HTTPException(404, f"no download {download_id!r}")
        return state.to_dict()

    @app.delete("/api/weights/{node_id}")
    async def remove_weights(node_id: str) -> dict[str, Any]:
        services.registry.get_class(node_id)  # 400 on unknown node
        return {"removed": services.weights.remove(node_id)}

    # -- presets -------------------------------------------------------------

    def preset_store() -> PresetStore:
        return services.presets

    @app.get("/api/presets")
    async def list_presets(store: PresetStore = Depends(preset_store)) -> list[dict[str, Any]]:
        return [p.to_dict() for p in store.list()]

    @app.get("/api/presets/{name}")
    async def get_preset(
        name: str, store: PresetStore = Depends(preset_store)
    ) -> dict[str, Any]:
        return store.get(name).to_dict()

    @app.put("/api/presets/{name}")
    async def save_preset(
        name: str, body: PresetBody, store: PresetStore = Depends(preset_store)
    ) -> dict[str, Any]:
        # Validate before persisting: a preset that cannot be executed is not a
        # preset, and finding that out at run time is worse than at save time.
        parse_pipeline(body.pipeline, services.registry)
        preset = Preset(name=name, pipeline=body.pipeline, description=body.description)
        store.save(preset)
        return preset.to_dict()

    @app.delete("/api/presets/{name}")
    async def delete_preset(
        name: str, store: PresetStore = Depends(preset_store)
    ) -> dict[str, Any]:
        return {"deleted": store.delete(name)}

    # Registered last: a mount is a fallback, and every /api/... route above
    # must keep matching first (ARCHITECTURE.md sections 1, 7).
    app.state.frontend_mounted = mount_frontend(app)

    return app
