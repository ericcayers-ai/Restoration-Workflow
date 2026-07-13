"""Generate synthetic test images for the regression corpus (ROADMAP.md Phase 9)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _save(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).save(path)


def generate_corpus(root: Path) -> list[Path]:
    """Write a fixed set of degraded synthetic images; returns paths created."""
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    h, w = 128, 128
    base = np.linspace(0.2, 0.8, w, dtype=np.float32)
    base = np.tile(base, (h, 1))
    rgb = np.stack([base, base * 0.9, base * 0.8], axis=-1)

    cases = {
        "blur": lambda: np.stack(
            [np.clip(rgb[:, :, c] + np.random.normal(0, 0.02, (h, w)), 0, 1) for c in range(3)],
            axis=-1,
        ),
        "noise": lambda: np.clip(rgb + np.random.normal(0, 0.08, rgb.shape), 0, 1),
        "lowres": lambda: np.array(
            Image.fromarray((rgb * 255).astype(np.uint8)).resize((32, 32))
        ).astype(np.float32)
        / 255.0,
        "jpeg": lambda: rgb,
        "low_light": lambda: rgb * 0.35,
        "face_heavy": lambda: rgb,
        "mixed": lambda: np.clip(rgb * 0.5 + np.random.normal(0, 0.05, rgb.shape), 0, 1),
    }

    for name, factory in cases.items():
        path = root / f"{name}.png"
        arr = factory()
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        _save(path, arr[:, :, :3])
        paths.append(path)
    return paths


if __name__ == "__main__":
    generate_corpus(Path(__file__).resolve().parent)
