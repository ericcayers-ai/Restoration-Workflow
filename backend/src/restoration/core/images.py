"""Image IO: one canonical in-memory format (float32 HWC RGB/RGBA in [0,1])."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from .types import ImageArray, ImageMeta

_SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def is_supported_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _SUPPORTED_SUFFIXES


def load_image(path: str | Path) -> ImageArray:
    with Image.open(path) as im:
        return pil_to_array(im)


def load_image_bytes(data: bytes) -> ImageArray:
    with Image.open(io.BytesIO(data)) as im:
        return pil_to_array(im)


def pil_to_array(im: Image.Image) -> ImageArray:
    if im.mode not in ("RGB", "RGBA", "L"):
        im = im.convert("RGBA" if "A" in im.mode or "transparency" in im.info else "RGB")
    arr = np.asarray(im, dtype=np.float32) / 255.0
    if arr.ndim == 2:  # grayscale -> RGB
        arr = np.stack([arr] * 3, axis=-1)
    return np.ascontiguousarray(arr)


def array_to_pil(image: ImageArray) -> Image.Image:
    arr = np.clip(image, 0.0, 1.0)
    arr = (arr * 255.0 + 0.5).astype(np.uint8)
    if arr.ndim == 2:
        return Image.fromarray(arr, mode="L")
    mode = {3: "RGB", 4: "RGBA"}.get(arr.shape[2])
    if mode is None:
        raise ValueError(f"cannot encode image with {arr.shape[2]} channels")
    return Image.fromarray(arr, mode=mode)


def save_image(image: ImageArray, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = array_to_pil(image)
    if path.suffix.lower() in (".jpg", ".jpeg") and im.mode == "RGBA":
        im = im.convert("RGB")
    im.save(path)
    return path


def encode_png(image: ImageArray) -> bytes:
    buf = io.BytesIO()
    array_to_pil(image).save(buf, format="PNG")
    return buf.getvalue()


def meta_of(image: ImageArray) -> ImageMeta:
    return ImageMeta.from_array(image)


def to_grayscale(image: ImageArray) -> ImageArray:
    """Luma (Rec. 601) from RGB(A), float32 HW."""
    rgb = image[..., :3]
    return rgb @ np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
