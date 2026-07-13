"""Classical scratch/dust restoration inspired by old-photo workflows.

This is the honest classical alternative to Microsoft's Bringing-Old-Photos
triplet model (ROADMAP.md 4.5.2) — morphological defect detection plus
OpenCV inpainting, no learned weights.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ...core.types import ImageArray


def restore_scratches(image: ImageArray, params: dict[str, Any]) -> ImageArray:
    """Detect thin scratches/specks and inpaint them."""
    rgb = image[:, :, :3].copy()
    gray = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)

    kernel_len = int(params.get("kernel", 15))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, kernel_len))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    residual = cv2.add(tophat, blackhat)

    thresh = int(params.get("threshold", 25))
    _, mask = cv2.threshold(residual, thresh, 255, cv2.THRESH_BINARY)
    dilate = int(params.get("dilate", 1))
    if dilate > 0:
        dk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate * 2 + 1, dilate * 2 + 1))
        mask = cv2.dilate(mask, dk)

    if not mask.any():
        return image

    method = cv2.INPAINT_TELEA if params.get("method", "telea") == "telea" else cv2.INPAINT_NS
    radius = int(params.get("radius", 3))
    bgr = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    restored = cv2.inpaint(bgr, mask, radius, method)
    out = cv2.cvtColor(restored, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    if image.shape[2] == 4:
        return np.concatenate([out, image[:, :, 3:4]], axis=2)
    return out
