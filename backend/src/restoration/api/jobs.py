"""Job queue and progress fan-out.

No Celery, no Redis: a single-user local app needs an in-process ``asyncio``
queue and nothing more (ARCHITECTURE.md section 2). One worker drains the queue,
so jobs execute one at a time; concurrency *within* a job (independent DAG
branches) is the executor's business, and GPU serialization is its semaphore's.

**Thread affinity is the thing to be careful about here.** Node inference is
blocking and runs under ``asyncio.to_thread``, so ``ctx.report_progress`` is
called from a worker thread. Touching an ``asyncio.Queue`` from there is
unsafe, so every event — including the terminal one raised on the loop thread —
is funnelled through ``loop.call_soon_threadsafe``. Routing *all* events through
the same hop is what keeps them in order; mixing direct and marshalled delivery
would let a terminal event overtake the progress events that preceded it.
"""

from __future__ import annotations

import asyncio
import enum
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import JobCancelled, RestorationError
from ..core.executor import PipelineSpec
from ..core.images import encode_png, save_image
from ..core.types import ImageArray, NodeStatus, ProgressEvent
from ..service import AppServices

_SENTINEL = object()
_MAX_EVENTS = 2000


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (JobState.DONE, JobState.ERROR, JobState.CANCELLED)


@dataclass
class Job:
    id: str
    spec: PipelineSpec
    image: ImageArray
    state: JobState = JobState.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    fallback: str | None = None
    analysis: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    cancel_requested: bool = False
    result_path: Path | None = None
    _previews: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "fallback": self.fallback,
            "analysis": self.analysis,
            "pipeline": self.spec.to_dict(),
            "result_url": f"/api/jobs/{self.id}/result" if self.result_path else None,
        }


class JobManager:
    def __init__(self, services: AppServices, root: Path | None = None) -> None:
        self.services = services
        self.root = Path(root) if root else services.data_dir / "jobs"
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[Job | None] = asyncio.Queue()
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._worker: asyncio.Task | None = None

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._worker is None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._worker = asyncio.create_task(self._run_worker())

    async def stop(self) -> None:
        if self._worker is None:
            return
        await self._queue.put(None)
        try:
            await asyncio.wait_for(self._worker, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):  # pragma: no cover
            self._worker.cancel()
        self._worker = None

    # -- public API ---------------------------------------------------------

    async def submit(
        self,
        spec: PipelineSpec,
        image: ImageArray,
        *,
        analysis: dict[str, Any] | None = None,
    ) -> Job:
        job = Job(id=uuid.uuid4().hex[:16], spec=spec, image=image, analysis=analysis)
        self._jobs[job.id] = job
        self._subscribers.setdefault(job.id, [])
        await self._queue.put(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.state.terminal:
            return False
        job.cancel_requested = True
        return True

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        """Replay this job's events, then stream new ones until it finishes."""
        job = self._jobs.get(job_id)
        if job is None:
            return

        queue: asyncio.Queue = asyncio.Queue()
        for event in list(job.events):
            queue.put_nowait(event)
        if job.state.terminal:
            queue.put_nowait(_SENTINEL)
        else:
            self._subscribers.setdefault(job_id, []).append(queue)

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    return
                yield item
        finally:
            subs = self._subscribers.get(job_id, [])
            if queue in subs:
                subs.remove(queue)

    # -- internals ----------------------------------------------------------

    def _publish(self, job: Job, event: dict[str, Any] | object) -> None:
        """Runs on the event loop thread only."""
        if event is not _SENTINEL:
            job.events.append(event)  # type: ignore[arg-type]
            if len(job.events) > _MAX_EVENTS:
                del job.events[: len(job.events) - _MAX_EVENTS]
        for queue in list(self._subscribers.get(job.id, [])):
            queue.put_nowait(event)

    def _emitter(
        self, job: Job, loop: asyncio.AbstractEventLoop
    ) -> Callable[[ProgressEvent], None]:
        def emit(event: ProgressEvent) -> None:
            try:
                loop.call_soon_threadsafe(self._publish, job, event.to_dict())
            except RuntimeError:  # pragma: no cover - loop already closed
                pass

        return emit

    def _preview_sink(self, job: Job) -> Callable[[ImageArray], str | None]:
        def sink(image: ImageArray) -> str | None:
            job._previews += 1
            index = job._previews
            path = self.root / job.id / f"preview_{index}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.write_bytes(encode_png(image))
            except OSError:  # pragma: no cover - a lost preview must not kill a run
                return None
            return f"/api/jobs/{job.id}/previews/{index}"

        return sink

    async def _run_worker(self) -> None:
        while True:
            job = await self._queue.get()
            if job is None:
                return
            try:
                await self._execute(job)
            finally:
                self._queue.task_done()

    async def _execute(self, job: Job) -> None:
        loop = asyncio.get_running_loop()
        emit = self._emitter(job, loop)

        if job.cancel_requested:
            self._finish(job, JobState.CANCELLED, emit)
            return

        job.state = JobState.RUNNING
        job.started_at = time.time()
        try:
            result = await self.services.executor.execute(
                job.spec,
                job.image,
                job_id=job.id,
                emit=emit,
                is_cancelled=lambda: job.cancel_requested,
                preview_sink=self._preview_sink(job),
            )
        except JobCancelled:
            self._finish(job, JobState.CANCELLED, emit)
        except RestorationError as exc:
            job.error = str(exc)
            job.fallback = getattr(exc, "fallback", None)
            self._finish(job, JobState.ERROR, emit)
        except Exception as exc:  # pragma: no cover - defensive; a job never kills the app
            job.error = f"unexpected {type(exc).__name__}: {exc}"
            self._finish(job, JobState.ERROR, emit)
        else:
            path = self.root / job.id / "result.png"
            await asyncio.to_thread(save_image, result, path)
            job.result_path = path
            self._finish(job, JobState.DONE, emit)

    def _finish(self, job: Job, state: JobState, emit: Callable[[ProgressEvent], None]) -> None:
        job.state = state
        job.finished_at = time.time()
        # Job-level terminal event: node_id "" is the job itself, per the
        # progress-event contract in ARCHITECTURE.md section 2.
        emit(
            ProgressEvent(
                node_id="",
                status=NodeStatus.DONE if state is JobState.DONE else NodeStatus.ERROR,
                progress=1.0 if state is JobState.DONE else 0.0,
                message=job.error or state.value,
            )
        )
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self._close_subscribers, job)

    def _close_subscribers(self, job: Job) -> None:
        for queue in list(self._subscribers.get(job.id, [])):
            queue.put_nowait(_SENTINEL)
        self._subscribers[job.id] = []
