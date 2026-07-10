"""Hardware detection & VRAM tiering (ARCHITECTURE.md section 5).

Probes torch.cuda / MPS at startup when torch is installed; degrades to
CPU-only otherwise. Never silently fails a run because of VRAM — the tier
gate produces a UI state with a human-readable reason instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .types import VramTier


@dataclass(frozen=True)
class GpuDevice:
    index: int
    name: str
    total_vram_mb: int


@dataclass(frozen=True)
class HardwareInfo:
    backend: str                       # "cuda" | "mps" | "cpu"
    devices: tuple[GpuDevice, ...] = field(default_factory=tuple)
    torch_available: bool = False
    torch_version: str | None = None

    @property
    def max_vram_mb(self) -> int:
        return max((d.total_vram_mb for d in self.devices), default=0)

    @property
    def device_string(self) -> str:
        if self.backend == "cuda":
            return "cuda"
        if self.backend == "mps":
            return "mps"
        return "cpu"

    @property
    def gpu_count(self) -> int:
        return len(self.devices)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "devices": [
                {"index": d.index, "name": d.name, "total_vram_mb": d.total_vram_mb}
                for d in self.devices
            ],
            "max_vram_mb": self.max_vram_mb,
            "torch_available": self.torch_available,
            "torch_version": self.torch_version,
        }


@dataclass(frozen=True)
class TierAvailability:
    """UI state for one node's tier on the detected hardware.

    state: "available" | "available_tiled" | "available_quantized" | "unavailable"
    Unavailable nodes are greyed with a reason, never hidden.
    """

    state: str
    reason: str | None = None
    badge: str | None = None

    @property
    def runnable(self) -> bool:
        return self.state != "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "reason": self.reason, "badge": self.badge}


class HardwareDetector:
    """Detects the compute backend once and answers tier-gating questions."""

    def __init__(self, force_cpu: bool | None = None):
        if force_cpu is None:
            force_cpu = os.environ.get("RESTORE_FORCE_CPU", "").lower() in ("1", "true", "yes")
        self._force_cpu = force_cpu
        self._info: HardwareInfo | None = None

    def detect(self, refresh: bool = False) -> HardwareInfo:
        if self._info is not None and not refresh:
            return self._info
        self._info = self._probe()
        return self._info

    def _probe(self) -> HardwareInfo:
        try:
            import torch  # noqa: PLC0415
        except ImportError:
            return HardwareInfo(backend="cpu", torch_available=False)

        version = getattr(torch, "__version__", None)
        if self._force_cpu:
            return HardwareInfo(backend="cpu", torch_available=True, torch_version=version)

        if torch.cuda.is_available():
            devices = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                devices.append(GpuDevice(
                    index=i,
                    name=props.name,
                    total_vram_mb=int(props.total_memory // (1024 * 1024)),
                ))
            return HardwareInfo(
                backend="cuda", devices=tuple(devices),
                torch_available=True, torch_version=version,
            )

        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            return HardwareInfo(backend="mps", torch_available=True, torch_version=version)

        return HardwareInfo(backend="cpu", torch_available=True, torch_version=version)

    # -- tier gating (the table in ARCHITECTURE.md section 5) -----------------

    def availability(self, tier: VramTier, uses_gpu: bool = True) -> TierAvailability:
        info = self.detect()

        if not uses_gpu:
            return TierAvailability(state="available")

        if info.backend == "cpu":
            if tier is VramTier.LOW:
                reason = None if info.torch_available else (
                    "inference dependencies not installed"
                )
                if reason:
                    return TierAvailability(state="unavailable", reason=reason)
                return TierAvailability(
                    state="available",
                    badge="cpu",
                    reason="No GPU detected; will run on CPU (slower).",
                )
            return TierAvailability(
                state="unavailable",
                reason="Requires a GPU; only LOW-tier (regression) models run on CPU.",
            )

        vram = info.max_vram_mb
        if vram < 8 * 1024:  # < 8GB
            if tier is VramTier.LOW:
                return TierAvailability(state="available")
            if tier is VramTier.MID:
                return TierAvailability(
                    state="available_tiled",
                    badge="tiled",
                    reason="Requires tiling on this GPU and will be slow.",
                )
            return TierAvailability(
                state="unavailable",
                reason=f"Needs at least {tier.min_vram_mb // 1024}GB VRAM; "
                       f"{vram // 1024}GB detected.",
            )
        if vram < 16 * 1024:  # 8-16GB
            if tier in (VramTier.LOW, VramTier.MID):
                return TierAvailability(state="available")
            if tier is VramTier.HIGH:
                return TierAvailability(
                    state="available_quantized",
                    badge="quantized",
                    reason="Runs quantized on this GPU.",
                )
            return TierAvailability(
                state="unavailable",
                reason=f"Needs at least 24GB VRAM; {vram // 1024}GB detected.",
            )
        # 16GB+: all tiers
        return TierAvailability(state="available")
