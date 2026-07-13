"""HAT — Hybrid Attention Transformer super-resolution (MODEL_STACK.md Phase 4).

Apache-2.0 SOTA SR via spandrel's ``HAT`` architecture. Weights are mirrored on
Hugging Face (Acly/hat) because the author's release is Google Drive/Baidu-only;
the mirror satisfies this repo's direct-download + sha256 pinning bar.
"""

from __future__ import annotations

from ..core.ordering import STAGE_UPSCALE
from ..core.types import LicenseInfo, LicenseKind, NodeCategory, VramTier, WeightFile
from .wrappers import spandrel_image_node

_HAT_LICENSE = LicenseInfo(
    spdx_id="Apache-2.0",
    kind=LicenseKind.PERMISSIVE,
    source_url="https://github.com/XPixelGroup/HAT/blob/main/LICENSE",
)


def _hat_weights(state_dict: dict) -> dict:
    inner = state_dict.get("params_ema") or state_dict.get("params")
    return inner if isinstance(inner, dict) else state_dict


HatNode = spandrel_image_node(
    id="hat",
    display_name="HAT",
    description=(
        "Hybrid Attention Transformer super-resolution; higher quality than SwinIR "
        "at the cost of more VRAM and slower inference."
    ),
    category=NodeCategory.REGRESSION,
    stage=STAGE_UPSCALE,
    vram_tier=VramTier.MID,
    license=_HAT_LICENSE,
    state_dict_transform=_hat_weights,
    weights=[
        WeightFile(
            filename="HAT_SRx4_ImageNet-pretrain.pth",
            size_bytes=85_128_960,
            sha256="4ee053c42461187846dc0e93aa5abd34591c0725a8e044a59000e92ee215e833",
            hf_repo_id="Acly/hat",
            hf_filename="HAT_SRx4_ImageNet-pretrain.pth",
        ),
    ],
)
