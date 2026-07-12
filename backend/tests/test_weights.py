"""WeightManager: the three gates from ARCHITECTURE.md section 6.

1. Licence acknowledgement before any non-permissive download.
2. A *hard* disk-space pre-check (huggingface_hub's own is advisory).
3. Checksum verification after download; a corrupt file never lands.

Downloads are driven through an httpx MockTransport, so the network is never
touched and the resume path can be asserted rather than assumed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from restoration.core.errors import (
    ChecksumMismatchError,
    InsufficientDiskSpaceError,
    LicenseNotAcknowledgedError,
    WeightsError,
    WeightsNotInstalledError,
)
from restoration.core.types import (
    BaseRestorationNode,
    LicenseInfo,
    LicenseKind,
    VramTier,
    WeightFile,
)
from restoration.core.weights import WeightManager, sha256_of

from .conftest import NonCommercialNode

PAYLOAD = b"the model weights" * 64
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def _node(weight: WeightFile, *, permissive: bool = True) -> BaseRestorationNode:
    class _Node(BaseRestorationNode):
        id = "under_test"
        display_name = "Under test"
        vram_tier = VramTier.LOW
        license = LicenseInfo(
            spdx_id="Apache-2.0" if permissive else "S-Lab-1.0",
            kind=LicenseKind.PERMISSIVE if permissive else LicenseKind.NON_COMMERCIAL,
            source_url="https://example.invalid/LICENSE",
        )
        weight_manifest = [weight]

    return _Node()


def _transport(payload: bytes = PAYLOAD, *, support_range: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        range_header = request.headers.get("Range")
        if range_header and support_range:
            start = int(range_header.removeprefix("bytes=").split("-")[0])
            body = payload[start:]
            return httpx.Response(206, content=body,
                                  headers={"Content-Length": str(len(body))})
        return httpx.Response(200, content=payload,
                              headers={"Content-Length": str(len(payload))})

    return httpx.MockTransport(handler)


def _manager(root: Path, **kwargs) -> WeightManager:
    return WeightManager(root, transport=_transport(**kwargs))


def _url_weight(sha: str | None = DIGEST) -> WeightFile:
    return WeightFile(
        filename="model.bin",
        size_bytes=len(PAYLOAD),
        sha256=sha,
        url="https://example.invalid/model.bin",
    )


# ---------------------------------------------------------------------------
# manifest shape
# ---------------------------------------------------------------------------

def test_weight_file_requires_exactly_one_source():
    with pytest.raises(ValueError, match="exactly one"):
        WeightFile(filename="a", size_bytes=1)
    with pytest.raises(ValueError, match="exactly one"):
        WeightFile(filename="a", size_bytes=1, url="u", hf_repo_id="r", hf_filename="f")

    WeightFile(filename="a", size_bytes=1, url="u")
    WeightFile(filename="a", size_bytes=1, hf_repo_id="r", hf_filename="f")


# ---------------------------------------------------------------------------
# gate 1: licence acknowledgement
# ---------------------------------------------------------------------------

def test_non_permissive_download_is_refused_without_acknowledgement(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight(), permissive=False)

    with pytest.raises(LicenseNotAcknowledgedError):
        manager.download(node)
    assert not manager.file_path(node.id, node.weight_manifest[0]).exists()


def test_acknowledgement_is_recorded_and_unblocks_the_download(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight(), permissive=False)

    assert manager.status(node).requires_acknowledgement is True
    assert manager.status(node).acknowledged is False

    manager.acknowledge_license(node)
    assert manager.is_acknowledged(node.id) is True
    assert manager.status(node).acknowledged is True

    manager.download(node)
    assert manager.is_installed(node)

    # Persisted across manager instances: a user acknowledges once, not per boot.
    assert WeightManager(tmp_path).is_acknowledged(node.id) is True


def test_permissive_nodes_need_no_acknowledgement(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight())
    assert manager.status(node).requires_acknowledgement is False
    manager.download(node)
    assert manager.is_installed(node)


def test_real_non_commercial_node_is_gated(tmp_path: Path):
    manager = _manager(tmp_path)
    with pytest.raises(LicenseNotAcknowledgedError):
        manager.download(NonCommercialNode())


# ---------------------------------------------------------------------------
# gate 2: disk space
# ---------------------------------------------------------------------------

def test_download_refused_when_the_file_will_not_fit(tmp_path: Path, monkeypatch):
    import shutil

    manager = _manager(tmp_path)
    node = _node(_url_weight())

    class _Usage:
        total = free = 1024  # far below the 1GiB margin

    monkeypatch.setattr(shutil, "disk_usage", lambda _p: _Usage)
    with pytest.raises(InsufficientDiskSpaceError) as excinfo:
        manager.download(node)

    assert excinfo.value.required == len(PAYLOAD)
    assert not manager.file_path(node.id, node.weight_manifest[0]).exists()


def test_disk_check_accounts_only_for_missing_files(tmp_path: Path):
    manager = _manager(tmp_path, )
    node = _node(_url_weight())
    manager.download(node)
    # Second call: nothing missing, so no space check and no re-download.
    assert manager.download(node) == manager.node_dir(node.id)


# ---------------------------------------------------------------------------
# gate 3: checksums
# ---------------------------------------------------------------------------

def test_checksum_mismatch_deletes_the_file(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight(sha="0" * 64))

    with pytest.raises(ChecksumMismatchError) as excinfo:
        manager.download(node)

    assert excinfo.value.actual == DIGEST
    assert not manager.file_path(node.id, node.weight_manifest[0]).exists()
    assert not manager.is_installed(node)


def test_declared_checksum_is_verified(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight())
    manager.download(node)
    assert sha256_of(manager.file_path(node.id, node.weight_manifest[0])) == DIGEST


def test_unpublished_checksum_is_pinned_on_first_use_then_enforced(tmp_path: Path):
    """Trust-on-first-use: verification is deferred, never skipped."""
    node = _node(_url_weight(sha=None))

    manager = _manager(tmp_path)
    manager.download(node)
    assert manager.status(node).files[0]["sha256"] == DIGEST

    # Now the upstream file changes underneath us; the pin must catch it.
    manager.remove(node.id)
    tampered = WeightManager(tmp_path, transport=_transport(b"different bytes entirely"))
    with pytest.raises(ChecksumMismatchError) as excinfo:
        tampered.download(node)
    assert excinfo.value.expected == DIGEST


def test_http_error_is_wrapped(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    manager = WeightManager(tmp_path, transport=httpx.MockTransport(handler))
    with pytest.raises(WeightsError, match="HTTP 404"):
        manager.download(_node(_url_weight()))


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------

def test_partial_download_resumes_from_the_existing_bytes(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight())
    weight = node.weight_manifest[0]

    part = manager.file_path(node.id, weight).with_suffix(".bin.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(PAYLOAD[:100])

    manager.download(node)
    assert manager.file_path(node.id, weight).read_bytes() == PAYLOAD
    assert not part.exists()


def test_resume_restarts_when_the_server_ignores_range(tmp_path: Path):
    manager = _manager(tmp_path, support_range=False)
    node = _node(_url_weight())
    weight = node.weight_manifest[0]

    part = manager.file_path(node.id, weight).with_suffix(".bin.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"stale partial content")

    manager.download(node)
    assert manager.file_path(node.id, weight).read_bytes() == PAYLOAD


# ---------------------------------------------------------------------------
# status / removal
# ---------------------------------------------------------------------------

def test_nodes_without_weights_are_always_installed(tmp_path: Path):
    from .conftest import RecordingNode

    manager = WeightManager(tmp_path)
    assert manager.is_installed(RecordingNode()) is True
    assert manager.ensure_installed(RecordingNode()) == manager.node_dir("recording")


def test_ensure_installed_raises_when_missing(tmp_path: Path):
    manager = WeightManager(tmp_path)
    with pytest.raises(WeightsNotInstalledError, match="restore weights download"):
        manager.ensure_installed(_node(_url_weight()))


def test_remove_reclaims_disk_and_reports_it(tmp_path: Path):
    manager = _manager(tmp_path)
    node = _node(_url_weight())
    manager.download(node)

    listed = manager.list_installed()
    assert listed == [{"node_id": "under_test", "size_bytes": len(PAYLOAD)}]

    assert manager.remove(node.id) is True
    assert manager.remove(node.id) is False
    assert manager.is_installed(node) is False


# ---------------------------------------------------------------------------
# default_data_dir() — RESTORE_HOME override, portable-frozen-exe, OS default
# ---------------------------------------------------------------------------

def test_restore_home_override_always_wins(monkeypatch, tmp_path: Path):
    from restoration.core.weights import default_data_dir

    monkeypatch.setenv("RESTORE_HOME", str(tmp_path / "custom"))
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert default_data_dir() == tmp_path / "custom"


def test_frozen_exe_defaults_next_to_the_executable(monkeypatch, tmp_path: Path):
    """The packaged desktop build keeps its data in the folder the user
    extracted, not scattered into the OS's per-user app-data location."""
    from restoration.core.weights import default_data_dir

    monkeypatch.delenv("RESTORE_HOME", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    exe_path = tmp_path / "RestorationWorkflow" / "RestorationWorkflow.exe"
    monkeypatch.setattr("sys.executable", str(exe_path))
    assert default_data_dir() == tmp_path / "RestorationWorkflow" / "data"


def test_non_frozen_ignores_the_executable_path(monkeypatch, tmp_path: Path):
    """A `pip install`-from-source run must not take the portable-exe branch
    even though sys.executable still points at *some* real interpreter."""
    from restoration.core.weights import default_data_dir

    monkeypatch.delenv("RESTORE_HOME", raising=False)
    monkeypatch.setattr("sys.frozen", False, raising=False)
    fake_exe_dir = tmp_path / "would-be-wrong"
    monkeypatch.setattr("sys.executable", str(fake_exe_dir / "python.exe"))
    assert default_data_dir() != fake_exe_dir / "data"
