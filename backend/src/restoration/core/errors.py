"""Exception hierarchy for the restoration engine.

Every error a caller (API layer, CLI, tests) is expected to branch on has its
own class here; nodes and core modules must not raise bare ``Exception``.
"""

from __future__ import annotations


class RestorationError(Exception):
    """Base class for all engine errors."""


class PipelineValidationError(RestorationError):
    """The submitted pipeline JSON is structurally invalid (unknown node type,
    cycle, duplicate id, bad edge, ...)."""


class NodeExecutionError(RestorationError):
    """A node failed while running.

    Carries an optional, concrete fallback suggestion (ARCHITECTURE.md section 4:
    never crash the run without offering one when we have one to offer).
    """

    def __init__(self, node_id: str, message: str, *, fallback: str | None = None):
        self.node_id = node_id
        self.fallback = fallback
        suffix = f" Suggested fallback: {fallback}" if fallback else ""
        super().__init__(f"Node '{node_id}' failed: {message}.{suffix}")


class OutOfMemoryError(NodeExecutionError):
    """A node hit a GPU out-of-memory condition that could not be recovered
    (tiling either unsupported or already attempted)."""


class JobCancelled(RestorationError):
    """Raised inside a running job when the user cancels it."""


class WeightsError(RestorationError):
    """Base class for weight-management failures."""


class LicenseNotAcknowledgedError(WeightsError):
    """Download refused: the model's license requires an explicit user
    acknowledgement that has not been recorded (ARCHITECTURE.md section 6)."""

    def __init__(self, node_id: str, license_id: str):
        self.node_id = node_id
        self.license_id = license_id
        super().__init__(
            f"Model '{node_id}' is licensed '{license_id}', which requires explicit "
            f"acknowledgement before its weights can be downloaded."
        )


class InsufficientDiskSpaceError(WeightsError):
    """Download refused up-front: declared manifest size exceeds free disk space."""

    def __init__(self, required: int, free: int):
        self.required = required
        self.free = free
        super().__init__(
            f"Refusing to start download: needs {required} bytes but only "
            f"{free} bytes are free at the weights cache location."
        )


class ChecksumMismatchError(WeightsError):
    """A downloaded weight file failed checksum verification. The file is
    deleted; it must never silently load."""

    def __init__(self, filename: str, expected: str, actual: str):
        self.filename = filename
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Checksum mismatch for '{filename}': expected {expected}, got {actual}. "
            f"The corrupt file has been removed."
        )


class WeightsNotInstalledError(WeightsError):
    """A node was asked to run but its weights are not installed."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(
            f"Weights for '{node_id}' are not installed. "
            f"Run: restore weights download {node_id}"
        )


class InferenceUnavailableError(NodeExecutionError):
    """torch/spandrel (the optional [inference] extra) is not installed, so a
    real model node cannot run. The engine itself keeps working."""

    def __init__(self, node_id: str):
        super().__init__(
            node_id,
            "inference dependencies are not installed "
            "(pip install 'restoration-workflow[inference]')",
        )


class PluginError(RestorationError):
    """A plugin failed to load. Never fatal to the app: the registry records
    the failure and continues (a broken third-party plugin must not take the
    backend down)."""
