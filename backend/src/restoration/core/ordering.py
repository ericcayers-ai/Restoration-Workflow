"""Canonical restoration-stage ordering.

A photo-restoration pipeline has a *right order*: fix exposure, remove
compression artifacts, denoise, upscale, restore faces, inpaint holes, then
compose — each stage cleaning the image before the next amplifies it. The
Advanced pipeline builder lets a user throw a bag of models together and press
"Auto-order"; this module is the single source of truth for what that produces.

Each node carries an optional ``pipeline_stage`` (see BaseRestorationNode). When
it's set, it wins; otherwise the stage is derived from the node's category. A new
model — a paper released next month, wrapped as a plugin — slots into the right
place by setting one integer, or gets a reasonable default for free from its
category. Nothing here hard-codes the built-in node ids beyond sensible defaults
that the nodes themselves can override.
"""

from __future__ import annotations

from typing import Any

from .registry import NodeRegistry
from .types import BaseRestorationNode, NodeCategory

# Lower runs earlier. Gaps left between stages so plugins can insert between
# them (e.g. a colour-correction pass at 35) without renumbering.
STAGE_EXPOSURE = 10   # low-light / exposure / white balance
STAGE_ARTIFACT = 20   # JPEG / compression artifact removal
STAGE_DENOISE = 30    # noise / grain
STAGE_COLORIZE = 35   # grayscale → colour (DDColor)
STAGE_UPSCALE = 40    # super-resolution / general enhancement
STAGE_FACE = 50       # face restoration
STAGE_MASK = 60       # mask generation
STAGE_INPAINT = 65    # inpainting / object removal (consumes a mask)
STAGE_INSTRUCT = 68   # instruction-guided Master Restorer finish pass
STAGE_COMPOSE = 70    # blend / compositing (runs last)

# Category defaults, used when a node doesn't declare its own stage. REGRESSION
# spans artifact/denoise/upscale, so a bare regression node is assumed to be an
# enhancement/upscale step unless it says otherwise.
_STAGE_BY_CATEGORY = {
    NodeCategory.GENERATIVE: STAGE_UPSCALE,
    NodeCategory.REGRESSION: STAGE_UPSCALE,
    NodeCategory.FACE: STAGE_FACE,
    NodeCategory.MASKING: STAGE_MASK,
    NodeCategory.INSTRUCT: STAGE_INSTRUCT,
    NodeCategory.ORCHESTRATION: STAGE_COMPOSE,
    # Legacy nodes must declare pipeline_stage explicitly; fall back to upscale.
    NodeCategory.LEGACY: STAGE_UPSCALE,
}


def stage_rank(node: BaseRestorationNode) -> int:
    """The node's position in the canonical order (lower = earlier)."""
    declared = getattr(node, "pipeline_stage", None)
    if declared is not None:
        return int(declared)
    return _STAGE_BY_CATEGORY.get(node.category, STAGE_UPSCALE)


def auto_order(nodes: list[BaseRestorationNode]) -> list[BaseRestorationNode]:
    """Stable-sort node *instances* into the canonical restoration order.

    Stable so that two models in the same stage keep the order the user added
    them in — auto-ordering never silently reshuffles a deliberate choice within
    a stage (e.g. GFPGAN before RestoreFormer)."""
    return sorted(nodes, key=stage_rank)


# In-box nodes with a required non-primary mask input. Selecting one without a
# mask source auto-inserts the box's mask generator right before it.
_MASK_CONSUMERS = frozenset({"lama", "powerpaint", "flux_fill"})
_MASK_PROVIDER = "mask_from_image"
_MASK_INPUT = "mask"


def auto_order_pipeline(
    node_types: list[str],
    registry: NodeRegistry,
    params: dict[str, dict[str, Any]] | None = None,
):
    """Build a runnable ``PipelineSpec`` from a bag of node *types*, ordered by
    ``stage_rank``. This is what the Advanced pipeline builder's "Auto-order"
    action calls: pick any models from the full stack, get back a pipeline in
    the right restoration order with no manual wiring."""
    from .executor import EdgeSpec, NodeSpec, PipelineSpec  # noqa: PLC0415 (avoid cycle)

    params = params or {}
    instances = [(t, registry.create(t)) for t in node_types]
    ordered = [t for t, _ in sorted(instances, key=lambda pair: stage_rank(pair[1]))]

    if any(c in ordered for c in _MASK_CONSUMERS) and _MASK_PROVIDER not in ordered:
        # Insert provider just before the first mask consumer.
        insert_at = min(ordered.index(c) for c in _MASK_CONSUMERS if c in ordered)
        ordered.insert(insert_at, _MASK_PROVIDER)

    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    mask_provider_id: str | None = None
    prev_id: str | None = None
    for i, node_type in enumerate(ordered):
        nid = f"n{i}_{node_type}"
        nodes.append(NodeSpec(id=nid, type=node_type, params=params.get(node_type, {})))

        if node_type == _MASK_PROVIDER:
            mask_provider_id = nid
            continue  # feeds a consumer's named input, not the main chain

        if node_type in _MASK_CONSUMERS and mask_provider_id is not None:
            edges.append(EdgeSpec(src=mask_provider_id, dst=nid, dst_input=_MASK_INPUT))
        if prev_id is not None:
            edges.append(EdgeSpec(src=prev_id, dst=nid))
        prev_id = nid

    return PipelineSpec(nodes=nodes, edges=edges)
