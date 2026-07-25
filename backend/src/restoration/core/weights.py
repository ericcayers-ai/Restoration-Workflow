"""Weight management (ARCHITECTURE.md section 6).

Wraps huggingface_hub for Hub-hosted files plus a generic URL path with
HTTP-Range resume for everything else. Before any download:

1. License acknowledgement gate — anything not permissively licensed requires
   an explicit, recorded acknowledgement (InvokeAI's attestation-click
   precedent), enforced *here*, not just in the UI.
2. Hard disk-space pre-check against the manifest's declared size —
   huggingface_hub's own check is advisory-only, so this gate is ours.
3. Checksum verification post-download — a corrupt/partial file never
   silently loads. Where upstream publishes no checksum, the hash is pinned
   on first download (trust-on-first-use) into checksums.lock.json and
   verified against that pin forever after.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .errors import (
    ChecksumMismatchError,
    InsufficientDiskSpaceError,
    LicenseNotAcknowledgedError,
    WeightsError,
    WeightsNotInstalledError,
)
from .types import BaseRestorationNode, WeightFile

# Refuse a download that would leave less than this free afterwards.
_FREE_SPACE_MARGIN_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB
_CHUNK = 1024 * 1024


def default_data_dir() -> Path:
    """Where weights, presets and the download cache live, overridable via RESTORE_HOME.

    The packaged desktop build (PyInstaller, ``sys.frozen``) defaults to a folder next
    to the executable rather than the OS's per-user app-data location — "the app is the
    folder you extracted" is the portable-app convention this class of tool already uses
    (ComfyUI's and Automatic1111's own portable Windows builds do the same), and it's what
    makes "back up/move the whole app" actually mean what it sounds like
    (ROADMAP.md Phase 4.5.6). A `pip install`-from-source run is not frozen and keeps the
    OS-conventional location below.
    """
    override = os.environ.get("RESTORE_HOME")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "RestorationWorkflow"
    if os.uname().sysname == "Darwin":  # pragma: no cover - platform specific
        return Path.home() / "Library" / "Application Support" / "RestorationWorkflow"
    xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(xdg) / "restoration-workflow"


def sha256_of(
    path: Path,
    *,
    check_cancel: Callable[[], None] | None = None,
) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            if check_cancel is not None:
                check_cancel()
            h.update(chunk)
    return h.hexdigest()


def hf_auth_headers() -> dict[str, str]:
    """Authorization headers for gated Hugging Face Hub downloads."""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


@dataclass
class WeightsStatus:
    node_id: str
    installed: bool
    files: list[dict[str, Any]]
    total_size_bytes: int
    acknowledged: bool
    requires_acknowledgement: bool
    missing_size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "installed": self.installed,
            "files": self.files,
            "total_size_bytes": self.total_size_bytes,
            "missing_size_bytes": self.missing_size_bytes,
            "acknowledged": self.acknowledged,
            "requires_acknowledgement": self.requires_acknowledgement,
        }


class WeightManager:
    """Owns the weights cache directory and every download that lands in it."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        free_space_margin: int = _FREE_SPACE_MARGIN_BYTES,
    ):
        self.root = Path(root) if root else default_data_dir() / "weights"
        self.root.mkdir(parents=True, exist_ok=True)
        self._transport = transport  # injectable for tests
        self._free_space_margin = free_space_margin
        self._ack_path = self.root / "acknowledgements.json"
        self._lock_path = self.root / "checksums.lock.json"

    # -- paths ----------------------------------------------------------------

    def node_dir(self, node_id: str) -> Path:
        return self.root / node_id

    def file_path(self, node_id: str, wf: WeightFile) -> Path:
        return self.node_dir(node_id) / wf.filename

    # -- license acknowledgement gate ------------------------------------------

    def _load_json(self, path: Path) -> dict[str, Any]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_json(self, path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def is_acknowledged(self, node_id: str) -> bool:
        return node_id in self._load_json(self._ack_path)

    def acknowledge_license(self, node: BaseRestorationNode) -> None:
        """Record the user's explicit acceptance of a non-permissive license."""
        acks = self._load_json(self._ack_path)
        acks[node.id] = {
            "spdx_id": node.license.spdx_id,
            "kind": node.license.kind.value,
            "source_url": node.license.source_url,
            "acknowledged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._save_json(self._ack_path, acks)

    def _gate_license(self, node: BaseRestorationNode) -> None:
        if node.license.requires_acknowledgement and not self.is_acknowledged(node.id):
            raise LicenseNotAcknowledgedError(node.id, node.license.spdx_id)

    # -- TOFU checksum pins ------------------------------------------------------

    def _pinned_sha256(self, node_id: str, filename: str) -> str | None:
        return self._load_json(self._lock_path).get(f"{node_id}/{filename}")

    def _pin_sha256(self, node_id: str, filename: str, digest: str) -> None:
        lock = self._load_json(self._lock_path)
        lock[f"{node_id}/{filename}"] = digest
        self._save_json(self._lock_path, lock)

    def _expected_sha256(self, node_id: str, wf: WeightFile) -> str | None:
        return wf.sha256 or self._pinned_sha256(node_id, wf.filename)

    # -- status ------------------------------------------------------------------

    def required_files(
        self,
        node: BaseRestorationNode,
        params: dict[str, Any] | None = None,
    ) -> list[WeightFile]:
        """Files needed to run ``node`` once with ``params`` (defaults if None)."""
        return node.required_weight_files(params)

    def is_installed(
        self,
        node: BaseRestorationNode,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """True when every file required for ``params`` (or defaults) is on disk.

        Multi-variant nodes only need their selected checkpoint — installing
        DDColor ``modelscope`` does not require ``artistic`` / ``paper``.
        """
        required = self.required_files(node, params)
        if not required:
            return True
        return all(self.file_path(node.id, wf).exists() for wf in required)

    def status(
        self,
        node: BaseRestorationNode,
        params: dict[str, Any] | None = None,
    ) -> WeightsStatus:
        required = {wf.filename for wf in self.required_files(node, params)}
        files = []
        for wf in node.weight_manifest:
            p = self.file_path(node.id, wf)
            files.append({
                "filename": wf.filename,
                "installed": p.exists(),
                "required_for_defaults": wf.filename in required,
                "size_bytes": p.stat().st_size if p.exists() else wf.size_bytes,
                "declared_size_bytes": wf.size_bytes,
                "sha256": self._expected_sha256(node.id, wf),
            })
        # Status totals use required (default/selected) bytes, not the full
        # multi-variant manifest — Settings "download sizes" stay honest.
        required_files = self.required_files(node, params)
        missing_required = [
            wf for wf in required_files if not self.file_path(node.id, wf).exists()
        ]
        return WeightsStatus(
            node_id=node.id,
            installed=self.is_installed(node, params),
            files=files,
            total_size_bytes=sum(wf.size_bytes for wf in required_files),
            missing_size_bytes=sum(wf.size_bytes for wf in missing_required),
            acknowledged=(not node.license.requires_acknowledgement)
                         or self.is_acknowledged(node.id),
            requires_acknowledgement=node.license.requires_acknowledgement,
        )

    def ensure_installed(
        self,
        node: BaseRestorationNode,
        params: dict[str, Any] | None = None,
    ) -> Path:
        """Path to the node's weights dir; raises if not installed (no implicit
        multi-gigabyte downloads mid-run — downloads are always explicit)."""
        if not self.is_installed(node, params):
            raise WeightsNotInstalledError(node.id)
        return self.node_dir(node.id)

    def remove(self, node_id: str) -> bool:
        """Delete a node's weights to reclaim disk space."""
        d = self.node_dir(node_id)
        if d.exists():
            shutil.rmtree(d)
            return True
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        out = []
        for d in sorted(self.root.iterdir()) if self.root.exists() else []:
            if d.is_dir():
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                out.append({"node_id": d.name, "size_bytes": size})
        return out

    # -- download -------------------------------------------------------------------

    def download(
        self,
        node: BaseRestorationNode,
        progress: Callable[[str, int, int], None] | None = None,
        *,
        params: dict[str, Any] | None = None,
        filenames: list[str] | None = None,
        check_cancel: Callable[[], None] | None = None,
        all_variants: bool = False,
    ) -> Path:
        """Download & verify weight files for the node.

        By default only files required for ``params`` (or the node's default
        params) are fetched. Pass ``all_variants=True`` to pull the full
        manifest, or ``filenames`` to target specific entries.

        ``progress(filename, bytes_done, bytes_total)`` is called as data lands.
        ``check_cancel`` is polled between chunks; raising ``JobCancelled`` aborts
        and leaves a ``.part`` file for resume (or deletes it when cleaned up by
        the download manager).
        Blocking; callers on the event loop run it in a thread.
        """
        self._gate_license(node)

        if filenames is not None:
            by_name = {wf.filename: wf for wf in node.weight_manifest}
            wanted = [by_name[name] for name in filenames if name in by_name]
        elif all_variants:
            wanted = list(node.weight_manifest)
        else:
            wanted = self.required_files(node, params)

        missing = [
            wf for wf in wanted
            if not self.file_path(node.id, wf).exists()
        ]
        if not missing:
            return self.node_dir(node.id)

        # Hard disk-space gate (huggingface_hub's own check is advisory-only).
        needed = sum(wf.size_bytes for wf in missing)
        free = shutil.disk_usage(self.root).free
        if needed + self._free_space_margin > free:
            raise InsufficientDiskSpaceError(required=needed, free=free)

        dest_dir = self.node_dir(node.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for wf in missing:
            if check_cancel is not None:
                check_cancel()
            self._download_one(node.id, wf, progress, check_cancel=check_cancel)
        return dest_dir

    def cleanup_partials(self, node_id: str) -> int:
        """Remove incomplete ``.part`` downloads for a node. Returns count deleted."""
        d = self.node_dir(node_id)
        if not d.is_dir():
            return 0
        removed = 0
        for path in d.rglob("*.part"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def _download_one(
        self,
        node_id: str,
        wf: WeightFile,
        progress: Callable[[str, int, int], None] | None,
        *,
        check_cancel: Callable[[], None] | None = None,
    ) -> None:
        dest = self.file_path(node_id, wf)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if wf.hf_repo_id is not None:
            self._download_hf(wf, dest, progress, check_cancel=check_cancel)
        else:
            self._download_url(wf, dest, progress, check_cancel=check_cancel)
        if check_cancel is not None:
            check_cancel()
        self._verify(node_id, wf, dest, check_cancel=check_cancel)

    def _download_hf(
        self, wf: WeightFile, dest: Path,
        progress: Callable[[str, int, int], None] | None,
        *,
        check_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Fetch Hub files through the URL path so progress and cancel work."""
        from huggingface_hub import hf_hub_url  # noqa: PLC0415

        url = hf_hub_url(repo_id=wf.hf_repo_id, filename=wf.hf_filename)
        url_wf = WeightFile(
            filename=wf.filename,
            size_bytes=wf.size_bytes,
            sha256=wf.sha256,
            url=url,
        )
        self._download_url(
            url_wf,
            dest,
            progress,
            check_cancel=check_cancel,
            extra_headers=hf_auth_headers(),
        )

    def _download_url(
        self, wf: WeightFile, dest: Path,
        progress: Callable[[str, int, int], None] | None,
        *,
        check_cancel: Callable[[], None] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        part = dest.with_suffix(dest.suffix + ".part")
        done = part.stat().st_size if part.exists() else 0
        headers = dict(extra_headers or {})
        if done:
            headers["Range"] = f"bytes={done}-"
        mode = "ab" if done else "wb"

        client_kwargs: dict[str, Any] = {"follow_redirects": True, "timeout": 60.0}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        with httpx.Client(**client_kwargs) as client:
            with client.stream("GET", wf.url, headers=headers) as resp:
                if done and resp.status_code == 200:
                    # Server ignored the Range header; restart from scratch.
                    done, mode = 0, "wb"
                elif resp.status_code not in (200, 206):
                    raise WeightsError(
                        f"download of '{wf.filename}' failed: HTTP {resp.status_code}"
                    )
                total = wf.size_bytes
                length = resp.headers.get("Content-Length")
                if length is not None:
                    total = done + int(length)
                with part.open(mode) as f:
                    for chunk in resp.iter_bytes(_CHUNK):
                        if check_cancel is not None:
                            check_cancel()
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(wf.filename, done, total)
        part.replace(dest)

    def _verify(
        self,
        node_id: str,
        wf: WeightFile,
        dest: Path,
        *,
        check_cancel: Callable[[], None] | None = None,
    ) -> None:
        actual = sha256_of(dest, check_cancel=check_cancel)
        expected = self._expected_sha256(node_id, wf)
        if expected is None:
            # Upstream publishes no checksum: pin on first use, verify forever after.
            self._pin_sha256(node_id, wf.filename, actual)
            return
        if actual.lower() != expected.lower():
            dest.unlink(missing_ok=True)
            raise ChecksumMismatchError(wf.filename, expected, actual)
