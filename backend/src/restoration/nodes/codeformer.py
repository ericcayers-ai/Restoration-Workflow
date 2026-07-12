"""CodeFormer — codebook-transformer face restoration, non-commercial (MODEL_STACK.md
Phase 4). The most popular/controllable face restorer in the ecosystem; its license is
what keeps it out of Simple Mode's default path (ROADMAP.md Phase 4 guardrail) rather
than any technical limitation — it is the flagship "maximum quality" opt-in face node in
Studio/Advanced Mode, reached only after the explicit acknowledgement gate
(ARCHITECTURE.md §6, core/weights.py).

Same detect -> FFHQ-align -> restore -> paste-back pipeline every other face node in the
box uses (``_faces.py``); loaded via spandrel's ``CodeFormer`` architecture, which lives
in ``spandrel_extra_arches`` rather than the main registry — MIT-licensed loader code,
entirely separate from the model's own NTU S-Lab 1.0 weight license. The checkpoint wraps
its weights under a ``params_ema`` key, same shape as SwinIR's checkpoints; a shared
transform unwraps it.

One real limitation of going through spandrel's generic interface rather than the native
repo: CodeFormer's own "fidelity" knob (``w``, trading identity-preservation against
generated detail) is baked to the architecture's default inside spandrel's ``call_fn`` and
is not exposed as a tunable parameter here. Worth revisiting if that knob turns out to
matter in practice.
"""

from __future__ import annotations

from ..core.types import LicenseInfo, LicenseKind, VramTier, WeightFile
from .face_nodes import YUNET_WEIGHT, FaceRestorationNode


def _codeformer_weights(state_dict: dict) -> dict:
    """CodeFormer's release checkpoint wraps the EMA weights under ``params_ema``."""
    inner = state_dict.get("params_ema")
    return inner if isinstance(inner, dict) else state_dict


class CodeFormerNode(FaceRestorationNode):
    id = "codeformer"
    display_name = "CodeFormer"
    description = (
        "Codebook-transformer face restoration; the most widely used and controllable "
        "face restorer, non-commercial licensed."
    )
    license = LicenseInfo(
        spdx_id="NTU-S-Lab-1.0",
        kind=LicenseKind.NON_COMMERCIAL,
        source_url="https://github.com/sczhou/CodeFormer/blob/master/LICENSE",
    )
    vram_tier = VramTier.MID
    model_filename = "codeformer.pth"
    state_dict_transform = staticmethod(_codeformer_weights)
    weight_manifest = [
        WeightFile(
            filename="codeformer.pth",
            size_bytes=376637898,
            sha256="1009e537e0c2a07d4cabce6355f53cb66767cd4b4297ec7a4a64ca4b8a5684b7",
            url="https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
        ),
        YUNET_WEIGHT,
    ]
