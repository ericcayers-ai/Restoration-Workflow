"""A one-call wrapper for new image-to-image restoration models.

The whole point of the node contract is that adding a model — a paper released
next month, a new checkpoint someone trained — should be small and mechanical,
not a code-writing exercise. If spandrel can load the checkpoint (its
MAIN_REGISTRY already covers 40+ architectures: HAT, DAT, DRCT, SwinIR, SCUNet,
NAFNet, Restormer via extra-arches, ...), wrapping it is a single call:

    from restoration.nodes.wrappers import spandrel_image_node
    from restoration.core.ordering import STAGE_UPSCALE
    from restoration.core.types import (
        LicenseInfo, LicenseKind, NodeCategory, VramTier, WeightFile,
    )

    DatNode = spandrel_image_node(
        id="dat",
        display_name="DAT",
        description="Dual Aggregation Transformer super-resolution.",
        category=NodeCategory.REGRESSION,
        stage=STAGE_UPSCALE,
        vram_tier=VramTier.MID,
        license=LicenseInfo("Apache-2.0", LicenseKind.PERMISSIVE, "https://.../LICENSE"),
        weights=[WeightFile(filename="DAT_x4.pth", size_bytes=..., sha256="...",
                            url="https://.../DAT_x4.pth")],
    )

Drop the returned class into ``BUILTIN_NODES`` (or register it from a plugin's
``manifest.json`` — same path, no core edits) and it appears in the model stack,
the downloads manager, and the auto-ordered pipeline builder with no further
work. ``state_dict_transform`` handles checkpoints whose key layout spandrel
doesn't expect out of the box (see swinir.py / lama.py for real uses); ``params``
adds knobs to the Inspector form. For anything more exotic than image->image,
subclass ``SpandrelNode`` or ``BaseRestorationNode`` directly.
"""

from __future__ import annotations

from typing import Any

from ..core.types import (
    ImageArray,
    LicenseInfo,
    NodeCategory,
    RunContext,
    VramTier,
    WeightFile,
)
from ._torch import SpandrelNode, StateDictTransform

_EMPTY_SCHEMA: dict[str, Any] = {
    "type": "object", "properties": {}, "additionalProperties": False,
}


def spandrel_image_node(
    *,
    id: str,
    display_name: str,
    description: str,
    category: NodeCategory,
    license: LicenseInfo,
    weights: list[WeightFile],
    stage: int | None = None,
    vram_tier: VramTier = VramTier.LOW,
    supports_tiling: bool = True,
    params: dict[str, Any] | None = None,
    state_dict_transform: StateDictTransform | None = None,
) -> type[SpandrelNode]:
    """Build a straightforward ``image -> image`` spandrel node class.

    ``params`` is the ``properties`` block of the Inspector's JSON-Schema form;
    tiling knobs are added automatically when ``supports_tiling`` is true, so a
    caller only lists model-specific parameters. Returns a new
    ``SpandrelNode`` subclass ready for ``BUILTIN_NODES`` or a plugin manifest.
    """
    properties = dict(params or {})
    if supports_tiling:
        properties.setdefault("tile", {
            "type": "integer", "minimum": 0, "default": 0, "title": "Tile size",
            "description": "0 disables tiling. Set automatically on GPU out-of-memory.",
        })
        properties.setdefault("tile_pad", {
            "type": "integer", "minimum": 0, "default": 32, "title": "Tile context padding",
            "description": "Extra context given to each tile and then discarded.",
        })
    schema = {"type": "object", "properties": properties, "additionalProperties": False}

    namespace: dict[str, Any] = {
        "id": id,
        "category": category,
        "pipeline_stage": stage,
        "display_name": display_name,
        "description": description,
        "license": license,
        "vram_tier": vram_tier,
        "supports_tiling": supports_tiling,
        "param_schema": schema if properties else _EMPTY_SCHEMA,
        "weight_manifest": list(weights),
    }
    if state_dict_transform is not None:
        namespace["state_dict_transform"] = staticmethod(state_dict_transform)

    def run_sync(
        self: SpandrelNode, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        return self._run_descriptor(image, params, ctx)

    namespace["run_sync"] = run_sync

    # A stable, importable class name derived from the node id.
    cls_name = "".join(part.capitalize() for part in id.replace("-", "_").split("_")) + "Node"
    return type(cls_name, (SpandrelNode,), namespace)
