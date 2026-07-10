"""Face restoration nodes: GFPGAN (fast) and RestoreFormer (quality).

Both are FFHQ-aligned 512x512 face models, so both share the detect -> align ->
restore -> paste-back pipeline in ``_faces.py``; they differ only in which
checkpoint they load and how spandrel expects that checkpoint to be shaped.

A note on RestoreFormer, because it contradicts the planning docs:
``MODEL_STACK.md`` names **RestoreFormer++** the default quality face node, and
the original rule table routed to a ``restoreformer_pp`` node. spandrel's
``RestoreFormer`` architecture cannot load the ++ checkpoint — its ``load()``
hardcodes ``head_size=8`` and ``attn_resolutions=(16,)``, while RestoreFormer++
carries additional decoder attention blocks (``decoder.up.4.attn.*``) and fails
``load_state_dict``. Shipping RestoreFormer v1 keeps the same Apache-2.0 licence
and the same codebook-transformer family; supporting ++ means vendoring its
architecture, which is Phase 4 work, not a Phase 1 line item.

Neither checkpoint is stored the way spandrel's detector expects, so each
supplies a ``state_dict_transform``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..core.types import (
    ImageArray,
    ImageMeta,
    LicenseInfo,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
    WeightFile,
)
from ._faces import (
    FACE_SIZE,
    YUNET_FILENAME,
    align_face,
    detect_faces,
    paste_face,
    select_faces,
)
from ._torch import (
    SpandrelNode,
    infer,
    merge_alpha,
    require_torch,
    split_alpha,
    to_numpy,
    to_tensor,
)

_YUNET_COMMIT = "f12e12798e8314f7c074a6656816c048dcc95b7a"
_YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
    f"{_YUNET_COMMIT}/models/face_detection_yunet/{YUNET_FILENAME}"
)

YUNET_WEIGHT = WeightFile(
    filename=YUNET_FILENAME,
    size_bytes=232589,
    sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    url=_YUNET_URL,
)

_FACE_PARAMS: dict[str, Any] = {
    "only_center_face": {
        "type": "boolean",
        "default": False,
        "title": "Only the centre face",
    },
    "max_faces": {
        "type": "integer",
        "minimum": 0,
        "default": 0,
        "title": "Maximum faces",
        "description": "0 restores every detected face, largest first.",
    },
    "min_face_size": {
        "type": "integer",
        "minimum": 0,
        "default": 32,
        "title": "Minimum face size (px)",
    },
    "strength": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "default": 1.0,
        "title": "Blend strength",
        "description": "How strongly the restored face replaces the original.",
    },
    "detection_threshold": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "default": 0.6,
        "title": "Detection confidence threshold",
    },
}


class FaceRestorationNode(SpandrelNode):
    """detect -> align -> restore -> paste back, for any FFHQ-512 face model."""

    category = NodeCategory.FACE
    vram_tier = VramTier.LOW
    # A face model always sees exactly one 512x512 crop, so tiling is meaningless
    # here: there is nothing for the executor's OOM fallback to subdivide.
    supports_tiling = False

    param_schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(_FACE_PARAMS),
        "additionalProperties": False,
    }

    def supports(self, image: ImageMeta) -> bool:
        return image.channels >= 3

    def weight_filename(self, params: dict[str, Any]) -> str:
        return self.model_filename

    #: The checkpoint this node restores faces with (the manifest also carries
    #: the shared YuNet detector).
    model_filename: str = ""

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        if ctx.weights_dir is None:  # pragma: no cover - executor always sets it
            raise ValueError("no weights directory")

        faces = detect_faces(
            self.id,
            image,
            Path(ctx.weights_dir) / YUNET_FILENAME,
            score_threshold=float(params.get("detection_threshold", 0.6)),
        )
        faces = select_faces(
            faces,
            image,
            only_center_face=bool(params.get("only_center_face", False)),
            min_face_size=int(params.get("min_face_size", 32)),
            max_faces=int(params.get("max_faces", 0)),
        )
        if not faces:
            # Not an error: the rule table only routes here when the analyzer saw
            # a face, but a node must behave sanely when driven directly from
            # Studio Mode or the CLI on an image without one.
            ctx.report_progress(1.0, "no faces detected; image passed through unchanged")
            return image

        torch, _ = require_torch(self.id)
        desc = self.descriptor(ctx, params)
        rgb, alpha = split_alpha(image)
        canvas = rgb.astype(np.float32, copy=True)
        strength = float(params.get("strength", 1.0))

        for i, face in enumerate(faces):
            ctx.check_cancelled()
            crop, affine = align_face(self.id, canvas, face)
            x = to_tensor(torch, crop, str(desc.device), desc.dtype)
            restored = to_numpy(infer(desc, x))
            if restored.shape[:2] != (FACE_SIZE, FACE_SIZE):  # pragma: no cover
                raise ValueError(
                    f"{self.id} produced a {restored.shape[:2]} face, expected "
                    f"{(FACE_SIZE, FACE_SIZE)}"
                )
            canvas = paste_face(self.id, canvas, restored, affine, strength=strength)
            ctx.report_progress((i + 1) / len(faces), f"restored face {i + 1}/{len(faces)}")

        return merge_alpha(canvas, alpha)


def _strip_prefix(state_dict: dict, prefix: str, drop: tuple[str, ...] = ()) -> dict:
    out = {
        key[len(prefix) :]: value
        for key, value in state_dict.items()
        if key.startswith(prefix)
    }
    for key in drop:
        out.pop(key, None)
    return out


class GfpganNode(FaceRestorationNode):
    id = "gfpgan"
    display_name = "GFPGAN"
    description = "Fast GAN-based face restoration; the default face node."
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/TencentARC/GFPGAN/blob/master/LICENSE",
    )
    model_filename = "GFPGANv1.4.pth"
    weight_manifest = [
        WeightFile(
            filename="GFPGANv1.4.pth",
            size_bytes=348632874,
            sha256="e2cd4703ab14f4d01fd1383a8a8b266f9a5833dacee8e6a79d3bf21a1b6be5ad",
            url="https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
        ),
        YUNET_WEIGHT,
    ]


def _restoreformer_state_dict(state_dict: dict) -> dict:
    """RestoreFormer ships a Lightning checkpoint whose weights live under a
    ``vqvae.`` attribute, plus a ``utility_counter`` buffer that isn't part of
    the module spandrel builds. Strip both so architecture detection sees the
    bare encoder/decoder keys it looks for."""
    inner = state_dict.get("state_dict", state_dict)
    return _strip_prefix(inner, "vqvae.", drop=("quantize.utility_counter",))


class RestoreFormerNode(FaceRestorationNode):
    id = "restoreformer"
    display_name = "RestoreFormer"
    description = (
        "Codebook-transformer face restoration; higher quality than GFPGAN on "
        "soft or heavily degraded faces."
    )
    license = LicenseInfo(
        spdx_id="Apache-2.0",
        kind=LicenseKind.PERMISSIVE,
        source_url="https://github.com/wzhouxiff/RestoreFormerPlusPlus/blob/master/LICENSE",
    )
    model_filename = "RestoreFormer.ckpt"
    state_dict_transform = staticmethod(_restoreformer_state_dict)
    weight_manifest = [
        WeightFile(
            filename="RestoreFormer.ckpt",
            size_bytes=290861237,
            sha256="4a193c716bc27cc0533d1b9307100c671e7b584ffa3ba6648182fea4b3228dff",
            url=(
                "https://github.com/wzhouxiff/RestoreFormerPlusPlus/releases/"
                "download/v1.0.0/RestoreFormer.ckpt"
            ),
        ),
        YUNET_WEIGHT,
    ]
