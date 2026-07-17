"""Background weight downloads with pollable progress.

A weight download is minutes of network I/O against a multi-gigabyte file, so it
cannot block a request. It also isn't a pipeline job, so it doesn't belong in the
job queue: a download must be able to proceed while a job runs, and a queued job
must never wait behind a 3GB transfer.

The licence acknowledgement and disk-space gates live in ``WeightManager`` and
are enforced there, not here — this class only decides *when* work runs, never
*whether* it is allowed to.
"""

from __future__ import annotations

import asyncio
import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import JobCancelled, RestorationError
from ..service import AppServices


class DownloadState(str, enum.Enum):
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Download:
    id: str
    node_id: str
    state: DownloadState = DownloadState.RUNNING
    filename: str | None = None
    bytes_done: int = 0
    bytes_total: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_requested: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    all_variants: bool = False

    @property
    def progress(self) -> float:
        if self.state is DownloadState.DONE:
            return 1.0
        if self.bytes_total <= 0:
            return 0.0
        return min(1.0, self.bytes_done / self.bytes_total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "state": self.state.value,
            "filename": self.filename,
            "bytes_done": self.bytes_done,
            "bytes_total": self.bytes_total,
            "progress": round(self.progress, 4),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "params": self.params,
            "all_variants": self.all_variants,
            "cancel_requested": self.cancel_requested,
        }


class DownloadManager:
    def __init__(self, services: AppServices) -> None:
        self.services = services
        self._downloads: dict[str, Download] = {}
        self._by_node: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._start_lock = asyncio.Lock()

    def get(self, download_id: str) -> Download | None:
        return self._downloads.get(download_id)

    def list(self) -> list[Download]:
        return sorted(self._downloads.values(), key=lambda d: d.started_at, reverse=True)

    async def start(
        self,
        node_id: str,
        *,
        params: dict[str, Any] | None = None,
        all_variants: bool = False,
        filenames: list[str] | None = None,
    ) -> Download:
        """Idempotent per node: asking twice returns the download already running.

        An asyncio lock serializes bookkeeping so concurrent POSTs for the same
        (or different) nodes cannot race two tasks into the same cache files.
        """
        async with self._start_lock:
            existing_id = self._by_node.get(node_id)
            if existing_id is not None:
                existing = self._downloads[existing_id]
                if existing.state is DownloadState.RUNNING:
                    return existing

            node = self.services.registry.create(node_id)  # raises on unknown node
            # Surface the licence gate synchronously, so the caller gets a 403 rather
            # than a background task that fails invisibly a moment later.
            if node.license.requires_acknowledgement and not self.services.weights.is_acknowledged(
                node_id
            ):
                from ..core.errors import LicenseNotAcknowledgedError  # noqa: PLC0415

                raise LicenseNotAcknowledgedError(node_id, node.license.spdx_id)

            resolved_params = {**node.default_params(), **(params or {})}
            if filenames is not None:
                by_name = {wf.filename: wf for wf in node.weight_manifest}
                wanted = [by_name[n] for n in filenames if n in by_name]
            elif all_variants:
                wanted = list(node.weight_manifest)
            else:
                wanted = self.services.weights.required_files(node, resolved_params)
            missing = [
                wf for wf in wanted
                if not self.services.weights.file_path(node.id, wf).exists()
            ]
            bytes_total = (
                sum(wf.size_bytes for wf in missing)
                if missing
                else sum(wf.size_bytes for wf in wanted)
            )

            download = Download(
                id=uuid.uuid4().hex[:16],
                node_id=node_id,
                bytes_total=bytes_total,
                params=resolved_params,
                all_variants=all_variants,
            )
            self._downloads[download.id] = download
            self._by_node[node_id] = download.id

            task = asyncio.create_task(
                self._run(download, node, resolved_params, all_variants, filenames)
            )
            self._tasks[download.id] = task
            task.add_done_callback(lambda _t, did=download.id: self._tasks.pop(did, None))
            return download

    def cancel(self, download_id: str) -> bool:
        """Request cooperative cancel. Returns True only if the download was running.

        State stays ``running`` until the worker observes ``cancel_requested``;
        pollers should read ``cancel_requested`` for an honest in-flight signal.
        """
        download = self._downloads.get(download_id)
        if download is None or download.state is not DownloadState.RUNNING:
            return False
        download.cancel_requested = True
        return True

    async def _run(
        self,
        download: Download,
        node: Any,
        params: dict[str, Any],
        all_variants: bool,
        filenames: list[str] | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        # Downloaded-so-far for files that already finished, so progress across a
        # multi-file manifest is monotonic rather than restarting per file.
        completed = {"bytes": 0, "current": ""}

        def on_progress(filename: str, done: int, total: int) -> None:
            if completed["current"] and filename != completed["current"]:
                completed["bytes"] = download.bytes_done
            completed["current"] = filename

            def update() -> None:
                download.filename = filename
                download.bytes_done = completed["bytes"] + done

            loop.call_soon_threadsafe(update)

        def check_cancel() -> None:
            if download.cancel_requested:
                raise JobCancelled(f"download {download.id} was cancelled")

        try:
            await asyncio.to_thread(
                self.services.weights.download,
                node,
                on_progress,
                params=params,
                filenames=filenames,
                check_cancel=check_cancel,
                all_variants=all_variants,
            )
        except JobCancelled:
            download.state = DownloadState.CANCELLED
            download.error = "cancelled"
            await asyncio.to_thread(self.services.weights.cleanup_partials, node.id)
        except RestorationError as exc:
            download.state = DownloadState.ERROR
            download.error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            download.state = DownloadState.ERROR
            download.error = f"unexpected {type(exc).__name__}: {exc}"
        else:
            download.state = DownloadState.DONE
            download.bytes_done = download.bytes_total
        finally:
            download.finished_at = time.time()
