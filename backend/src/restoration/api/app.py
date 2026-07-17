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
from ..core.ordering import auto_order_pipeline
from ..core.quality import QualityTier
from ..core.workflow_text import parse_workflow, serialize_workflow
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


class AutoOrderBody(BaseModel):
    node_types: list[str] = Field(..., description="Node type ids to arrange into a pipeline.")
    params: dict[str, dict[str, Any]] = Field(default_factory=dict)


class EnsembleBody(BaseModel):
    prompt_preset_id: str | None = None
    instruction: str | None = None
    mode: str = Field(
        default="guide_and_finish",
        description="finish_only | instruct_only | guide_and_finish",
    )
    profile: dict[str, Any] | None = Field(
        default=None,
        description="Optional analyzer profile from /api/analyze for ensembles.",
    )


class DownloadBody(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    all_variants: bool = False
    filenames: list[str] | None = None


class WorkflowExportBody(BaseModel):
    pipeline: dict[str, Any]
    name: str = ""
    description: str = ""


class WorkflowImportBody(BaseModel):
    text: str


def _form_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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

    def _parse_quality_tier(raw: str) -> QualityTier:
        try:
            return QualityTier(raw)
        except ValueError:
            raise HTTPException(
                400, f"unknown quality_tier {raw!r}; expected draft, balanced, or high"
            ) from None

    @app.post("/api/analyze")
    async def analyze(
        image: UploadFile = File(...), quality_tier: str = Form("balanced")
    ) -> dict[str, Any]:
        array = await _read_image(image)
        tier = _parse_quality_tier(quality_tier)
        auto = await asyncio.to_thread(services.analyze, array, tier)
        payload = auto.to_dict()
        payload["missing_weights"] = services.missing_weights(auto.spec)
        return payload

    # -- VLM Auto (Phase 4) --------------------------------------------------

    @app.get("/api/vlm")
    async def vlm_status() -> dict[str, Any]:
        return services.vlm.status()

    @app.post("/api/vlm/download", status_code=202)
    async def vlm_download() -> dict[str, Any]:
        download = await downloads.start("vlm")
        return download.to_dict()

    @app.delete("/api/vlm")
    async def vlm_remove() -> dict[str, Any]:
        return {"removed": services.vlm.remove(), "vlm": services.vlm.status()}

    @app.post("/api/auto/describe")
    async def auto_describe(
        image: UploadFile = File(...),
        force_heuristic: str = Form("false"),
    ) -> dict[str, Any]:
        array = await _read_image(image)
        force = str(force_heuristic).lower() in ("1", "true", "yes")
        description = await asyncio.to_thread(
            services.describe_photo, array, force_heuristic=force
        )
        return {
            "description": description.to_dict(),
            "vlm": services.vlm.status(),
        }

    @app.post("/api/auto/plan")
    async def auto_plan(
        image: UploadFile = File(...),
        goal: str = Form(""),
        quality_tier: str = Form("balanced"),
        fallback: str = Form("skill"),
        force_heuristic: str = Form("false"),
    ) -> dict[str, Any]:
        """Skill-driven Auto plan (VLM describe when installed; rule_table on request)."""
        array = await _read_image(image)
        tier = _parse_quality_tier(quality_tier)
        mode = (fallback or "skill").strip().lower()
        if mode not in ("skill", "rule_table"):
            raise HTTPException(400, "fallback must be 'skill' or 'rule_table'")
        force = str(force_heuristic).lower() in ("1", "true", "yes")
        return await asyncio.to_thread(
            services.plan_auto,
            array,
            goal=_form_str(goal),
            quality_tier=tier,
            fallback=mode,
            force_heuristic=force,
        )

    @app.post("/api/auto/suggest")
    async def auto_suggest(
        image: UploadFile = File(...),
        goal: str = Form(""),
        force_heuristic: str = Form("false"),
    ) -> dict[str, Any]:
        """Dynamic Studio preset suggestions from describe + goal."""
        array = await _read_image(image)
        force = str(force_heuristic).lower() in ("1", "true", "yes")
        return await asyncio.to_thread(
            services.suggest_auto_presets,
            array,
            goal=_form_str(goal),
            force_heuristic=force,
        )

    # -- jobs ----------------------------------------------------------------

    @app.post("/api/jobs", status_code=202)
    async def submit_job(
        image: UploadFile = File(...),
        pipeline: str | None = Form(None),
        preset: str | None = Form(None),
        quality_tier: str = Form("balanced"),
    ) -> dict[str, Any]:
        """Submit a pipeline. With neither ``pipeline`` nor ``preset``, the
        degradation analyzer picks one — that is Simple Mode's entire request.
        ``quality_tier`` only affects that automatic pick; an explicit pipeline
        or preset already says exactly what to run."""
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
            preset_obj = services.presets.get(preset)
            gate = services.preset_licence_gate(preset_obj.pipeline)
            if not gate["ready"]:
                raise LicenseNotAcknowledgedError(
                    ",".join(gate["unacknowledged_node_ids"]),
                    "restricted",
                )
            spec = parse_pipeline(preset_obj.pipeline, services.registry)
        else:
            tier = _parse_quality_tier(quality_tier)
            auto = await asyncio.to_thread(services.analyze, array, tier)
            spec = auto.spec
            analysis = auto.to_dict()

        # Explicit pipelines can also include gated nodes — close the bypass.
        unacked = services.unacknowledged_nodes(spec)
        if unacked:
            raise LicenseNotAcknowledgedError(",".join(unacked), "restricted")

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

    @app.delete("/api/jobs/{job_id}")
    async def delete_job(job_id: str) -> dict[str, Any]:
        _job_or_404(job_id)
        return {"deleted": jobs.delete(job_id)}

    @app.post("/api/jobs/cleanup")
    async def cleanup_jobs() -> dict[str, Any]:
        purged = jobs.cleanup()
        return {"purged": purged, "remaining": len(jobs.list())}

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
        overview = {
            "cache_dir": str(services.weights.root),
            "nodes": [
                services.weights.status(node).to_dict()
                for node in services.registry.all_nodes()
                if node.weight_manifest
            ],
            "installed": services.weights.list_installed(),
        }
        overview["totals"] = services.weight_download_totals()
        return overview

    @app.get("/api/instructir/prompts")
    async def instructir_prompts() -> dict[str, Any]:
        from ..core.ensemble import prompt_library_summary  # noqa: PLC0415

        return prompt_library_summary()

    @app.post("/api/pipelines/ensemble")
    async def build_ensemble(request: Request) -> dict[str, Any]:
        """Build a guided ensemble.

        Accepts JSON (``EnsembleBody``, optional ``profile``) or multipart with
        an image so Studio can pass analyzer-aware context in one round-trip.
        """
        ctype = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in ctype:
            form = await request.form()
            upload = form.get("image")
            array = None
            if upload is not None and hasattr(upload, "read"):
                data = await upload.read()  # type: ignore[union-attr]
                if data:
                    array = load_image_bytes(data)
            return services.build_ensemble(
                array,
                prompt_preset_id=_form_str(form.get("prompt_preset_id")),
                instruction=_form_str(form.get("instruction")),
                mode=_form_str(form.get("mode")) or "guide_and_finish",
            )
        payload = await request.json()
        body = EnsembleBody.model_validate(payload)
        return services.build_ensemble(
            prompt_preset_id=body.prompt_preset_id,
            instruction=body.instruction,
            mode=body.mode,
            profile_dict=body.profile,
        )

    @app.post("/api/weights/{node_id}/acknowledge")
    async def acknowledge(node_id: str, body: AcknowledgeBody) -> dict[str, Any]:
        if not body.accepted:
            raise HTTPException(400, "acknowledgement requires accepted=true")
        node = services.registry.create(node_id)
        services.weights.acknowledge_license(node)
        return services.weights.status(node).to_dict()

    @app.post("/api/weights/{node_id}/download", status_code=202)
    async def download_weights(node_id: str, request: Request) -> dict[str, Any]:
        opts = DownloadBody()
        raw = await request.body()
        if raw:
            opts = DownloadBody.model_validate(json.loads(raw))
        download = await downloads.start(
            node_id,
            params=opts.params,
            all_variants=opts.all_variants,
            filenames=opts.filenames,
        )
        return download.to_dict()

    @app.get("/api/weights/downloads")
    async def list_downloads() -> list[dict[str, Any]]:
        return [d.to_dict() for d in downloads.list()]

    @app.get("/api/weights/downloads/{download_id}")
    async def download_status(download_id: str) -> dict[str, Any]:
        state = downloads.get(download_id)
        if state is None:
            raise HTTPException(404, f"no download {download_id!r}")
        return state.to_dict()

    @app.post("/api/weights/downloads/{download_id}/cancel")
    async def cancel_download(download_id: str) -> dict[str, Any]:
        state = downloads.get(download_id)
        if state is None:
            raise HTTPException(404, f"no download {download_id!r}")
        accepted = downloads.cancel(download_id)
        # Re-read so the response reflects cancel_requested without pretending
        # the worker has already reached the terminal cancelled state.
        current = downloads.get(download_id) or state
        return {
            "cancelled": accepted,
            "state": current.state.value,
            "cancel_requested": current.cancel_requested,
        }

    @app.delete("/api/weights/{node_id}")
    async def remove_weights(node_id: str) -> dict[str, Any]:
        services.registry.get_class(node_id)  # 400 on unknown node
        return {"removed": services.weights.remove(node_id)}

    # -- presets -------------------------------------------------------------

    def preset_store() -> PresetStore:
        return services.presets

    @app.get("/api/presets")
    async def list_presets(
        store: PresetStore = Depends(preset_store),
        include_gated: bool = True,
    ) -> list[dict[str, Any]]:
        out = []
        for preset in store.list():
            described = services.describe_preset(preset)
            if not include_gated and not described["licence"]["ready"]:
                continue
            out.append(described)
        return out

    @app.get("/api/presets/{name}")
    async def get_preset(
        name: str, store: PresetStore = Depends(preset_store)
    ) -> dict[str, Any]:
        return services.describe_preset(store.get(name))

    @app.put("/api/presets/{name}")
    async def save_preset(
        name: str, body: PresetBody, store: PresetStore = Depends(preset_store)
    ) -> dict[str, Any]:
        # Validate before persisting: a preset that cannot be executed is not a
        # preset, and finding that out at run time is worse than at save time.
        parse_pipeline(body.pipeline, services.registry)
        preset = Preset(name=name, pipeline=body.pipeline, description=body.description)
        store.save(preset)
        return services.describe_preset(preset)

    @app.delete("/api/presets/{name}")
    async def delete_preset(
        name: str, store: PresetStore = Depends(preset_store)
    ) -> dict[str, Any]:
        return {"deleted": store.delete(name)}

    # -- pipeline building (Advanced mode: auto-order + .txt workflows) ------

    @app.post("/api/pipelines/auto-order")
    async def auto_order(body: AutoOrderBody) -> dict[str, Any]:
        """Arrange a bag of chosen model types into a runnable pipeline in the
        canonical restoration order (core/ordering.py) — the Advanced pipeline
        builder's "Auto-order" action."""
        spec = auto_order_pipeline(body.node_types, services.registry, body.params)
        return spec.to_dict()

    @app.post("/api/workflows/export")
    async def export_workflow(body: WorkflowExportBody) -> dict[str, Any]:
        spec = parse_pipeline(body.pipeline, services.registry)
        text = serialize_workflow(spec, name=body.name, description=body.description)
        return {"text": text}

    @app.post("/api/workflows/import")
    async def import_workflow(body: WorkflowImportBody) -> dict[str, Any]:
        spec = parse_workflow(body.text, services.registry)
        return spec.to_dict()

    # Registered last: a mount is a fallback, and every /api/... route above
    # must keep matching first (ARCHITECTURE.md sections 1, 7).
    app.state.frontend_mounted = mount_frontend(app)

    return app
