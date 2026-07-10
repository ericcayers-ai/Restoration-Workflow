"""Face detection, alignment and paste-back for the face-restoration nodes.

GFPGAN and RestoreFormer are trained on FFHQ-aligned 512x512 face crops; handed
a whole photograph they produce nothing useful. The real work of a face node is
therefore this module, not the model call: detect faces, warp each one into the
FFHQ reference frame, restore it, warp it back, and composite it into the
original with a soft edge so the seam doesn't show.

Detection uses OpenCV's bundled YuNet (``cv2.FaceDetectorYN``), an MIT-licensed
ONNX detector from opencv_zoo. It is chosen over the Haar cascade the analyzer
uses because it returns the five landmarks alignment needs; the cascade returns
a bounding box only. It is a *detector*, never a restoration model — the
distinction ARCHITECTURE.md section 4 draws.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..core.errors import NodeExecutionError
from ..core.types import ImageArray

YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"

# The FFHQ 512x512 five-point reference, as used by facexlib's
# FaceRestoreHelper and therefore by every GFPGAN/RestoreFormer checkpoint.
# Row order is (right eye, left eye, nose tip, right mouth corner, left mouth
# corner) in *image* coordinates — "right eye" is the subject's right eye, which
# appears on the left of the image and so carries the smaller x. YuNet emits its
# five landmarks in exactly this order, so no reordering is needed.
FFHQ_TEMPLATE_512 = np.array(
    [
        [192.98138, 239.94708],
        [318.90277, 240.19360],
        [256.63416, 314.01935],
        [201.26117, 371.41043],
        [313.08905, 371.15118],
    ],
    dtype=np.float32,
)

FACE_SIZE = 512
# Long-side size the detector runs at. Detection quality is scale-sensitive and
# YuNet was trained around this range; landmarks are mapped back afterwards.
_DETECT_LONG_SIDE = 640


def require_cv2(node_id: str) -> Any:
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise NodeExecutionError(
            node_id,
            "face nodes need OpenCV (pip install 'restoration-workflow[inference]')",
        ) from exc
    return cv2


@dataclass(frozen=True)
class DetectedFace:
    """One detection, in the coordinate space of the image passed to detect()."""

    bbox: tuple[float, float, float, float]  # x, y, w, h
    landmarks: np.ndarray                    # (5, 2) float32
    score: float

    @property
    def size(self) -> float:
        return max(self.bbox[2], self.bbox[3])


def _to_bgr_u8(rgb: ImageArray) -> np.ndarray:
    arr = (np.clip(rgb[..., :3], 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return arr[..., ::-1].copy()


def detect_faces(
    node_id: str,
    image: ImageArray,
    yunet_path: str | Path,
    *,
    score_threshold: float = 0.6,
    nms_threshold: float = 0.3,
) -> list[DetectedFace]:
    """Detect faces and their five landmarks, in ``image``'s coordinate space."""
    cv2 = require_cv2(node_id)
    yunet_path = Path(yunet_path)
    if not yunet_path.exists():
        raise NodeExecutionError(node_id, f"face detector weights missing: {yunet_path}")

    h, w = image.shape[:2]
    scale = min(1.0, _DETECT_LONG_SIDE / max(h, w))
    bgr = _to_bgr_u8(image)
    if scale < 1.0:
        bgr = cv2.resize(bgr, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                         interpolation=cv2.INTER_AREA)

    dh, dw = bgr.shape[:2]
    try:
        detector = cv2.FaceDetectorYN.create(
            str(yunet_path), "", (dw, dh), score_threshold, nms_threshold, 5000
        )
        _, raw = detector.detect(bgr)
    except cv2.error as exc:  # pragma: no cover - depends on opencv build
        raise NodeExecutionError(node_id, f"face detection failed: {exc}") from exc

    if raw is None:
        return []

    inv = 1.0 / scale if scale > 0 else 1.0
    faces = []
    for row in raw:
        bbox = tuple(float(v) * inv for v in row[0:4])
        lms = np.asarray(row[4:14], dtype=np.float32).reshape(5, 2) * inv
        faces.append(DetectedFace(bbox=bbox, landmarks=lms, score=float(row[14])))  # type: ignore[arg-type]
    return faces


def align_face(
    node_id: str, image: ImageArray, face: DetectedFace
) -> tuple[ImageArray, np.ndarray]:
    """Warp a detected face into the 512x512 FFHQ frame.

    Returns the crop and the 2x3 affine that produced it (needed to invert).
    """
    cv2 = require_cv2(node_id)
    affine, _ = cv2.estimateAffinePartial2D(
        face.landmarks, FFHQ_TEMPLATE_512, method=cv2.LMEDS
    )
    if affine is None:
        raise NodeExecutionError(node_id, "could not estimate a face alignment transform")

    crop = cv2.warpAffine(
        image[..., :3].astype(np.float32),
        affine,
        (FACE_SIZE, FACE_SIZE),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return np.ascontiguousarray(crop, dtype=np.float32), affine


def paste_face(
    node_id: str,
    canvas: ImageArray,
    restored_face: ImageArray,
    affine: np.ndarray,
    *,
    strength: float = 1.0,
    feather: int = 24,
) -> ImageArray:
    """Composite a restored 512x512 face back into ``canvas`` through ``affine``.

    The mask is built in the aligned frame (where the face is always centred and
    axis-aligned), then warped back with the same inverse transform as the face
    itself, so mask and pixels can never drift apart.
    """
    cv2 = require_cv2(node_id)
    h, w = canvas.shape[:2]
    inverse = cv2.invertAffineTransform(affine)

    warped = cv2.warpAffine(
        restored_face, inverse, (w, h), flags=cv2.INTER_LINEAR, borderValue=0.0
    )

    mask = np.ones((FACE_SIZE, FACE_SIZE), dtype=np.float32)
    if feather > 0:
        mask = cv2.erode(mask, np.ones((feather, feather), np.uint8))
        blur = feather * 2 + 1
        mask = cv2.GaussianBlur(mask, (blur, blur), 0)
    warped_mask = cv2.warpAffine(mask, inverse, (w, h), flags=cv2.INTER_LINEAR, borderValue=0.0)
    warped_mask = np.clip(warped_mask, 0.0, 1.0) * float(np.clip(strength, 0.0, 1.0))
    alpha = warped_mask[..., None]

    out = canvas.copy()
    out[..., :3] = warped * alpha + canvas[..., :3] * (1.0 - alpha)
    return out


def select_faces(
    faces: list[DetectedFace],
    image: ImageArray,
    *,
    only_center_face: bool = False,
    min_face_size: int = 0,
    max_faces: int = 0,
) -> list[DetectedFace]:
    """Filter/rank detections the way the node's params ask for."""
    kept = [f for f in faces if f.size >= min_face_size]
    if not kept:
        return []

    if only_center_face:
        h, w = image.shape[:2]
        cx, cy = w / 2.0, h / 2.0

        def center_distance(f: DetectedFace) -> float:
            fx = f.bbox[0] + f.bbox[2] / 2.0
            fy = f.bbox[1] + f.bbox[3] / 2.0
            return (fx - cx) ** 2 + (fy - cy) ** 2

        return [min(kept, key=center_distance)]

    kept.sort(key=lambda f: f.size, reverse=True)
    if max_faces > 0:
        kept = kept[:max_faces]
    return kept
