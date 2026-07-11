"""Canonical restoration-stage ordering and the Advanced pipeline builder's
"Auto-order" action.

The real registry is used (not the fakes in conftest) because the whole point
of this module is ordering the *actual* shipped nodes correctly — a fake node
graph would test the sorting algorithm but not the thing that matters, which is
whether fbcnn really precedes scunet really precedes swinir really precedes
gfpgan in the app users get.
"""

from __future__ import annotations

from restoration.core.executor import parse_pipeline
from restoration.core.ordering import (
    STAGE_ARTIFACT,
    STAGE_DENOISE,
    STAGE_FACE,
    STAGE_INPAINT,
    STAGE_MASK,
    STAGE_UPSCALE,
    auto_order_pipeline,
    stage_rank,
)
from restoration.core.registry import NodeRegistry


def real_registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register_builtins()
    return reg


def test_stage_rank_matches_the_documented_restoration_order():
    reg = real_registry()
    assert stage_rank(reg.create("fbcnn")) == STAGE_ARTIFACT
    assert stage_rank(reg.create("swinir_jpeg")) == STAGE_ARTIFACT
    assert stage_rank(reg.create("scunet")) == STAGE_DENOISE
    assert stage_rank(reg.create("swinir_denoise")) == STAGE_DENOISE
    assert stage_rank(reg.create("realesrgan")) == STAGE_UPSCALE
    assert stage_rank(reg.create("swinir")) == STAGE_UPSCALE
    assert stage_rank(reg.create("gfpgan")) == STAGE_FACE
    assert stage_rank(reg.create("restoreformer")) == STAGE_FACE
    assert stage_rank(reg.create("mask_from_image")) == STAGE_MASK
    assert stage_rank(reg.create("lama")) == STAGE_INPAINT


def test_auto_order_reorders_a_scrambled_selection():
    reg = real_registry()
    # restoreformer and gfpgan are both STAGE_FACE; the sort is stable, so they
    # keep the relative order they were picked in (restoreformer before gfpgan
    # here) while fbcnn/realesrgan move ahead of both by stage.
    spec = auto_order_pipeline(["restoreformer", "realesrgan", "fbcnn", "gfpgan"], reg)
    assert [n.type for n in spec.nodes] == ["fbcnn", "realesrgan", "restoreformer", "gfpgan"]
    # A straight chain: each node feeds the next, nothing branches.
    assert [(e.src, e.dst) for e in spec.edges] == [
        (spec.nodes[0].id, spec.nodes[1].id),
        (spec.nodes[1].id, spec.nodes[2].id),
        (spec.nodes[2].id, spec.nodes[3].id),
    ]


def test_auto_order_keeps_stable_order_within_a_stage():
    """Two models in the same stage (both face nodes) keep the order the user
    picked them in — auto-order must not silently reshuffle a deliberate choice."""
    reg = real_registry()
    a = auto_order_pipeline(["gfpgan", "restoreformer"], reg)
    b = auto_order_pipeline(["restoreformer", "gfpgan"], reg)
    assert [n.type for n in a.nodes] == ["gfpgan", "restoreformer"]
    assert [n.type for n in b.nodes] == ["restoreformer", "gfpgan"]


def test_auto_order_inserts_a_mask_source_for_lama():
    """Selecting LaMa alone (no mask node) must not produce an unrunnable
    pipeline — the mask generator is inserted automatically."""
    reg = real_registry()
    spec = auto_order_pipeline(["fbcnn", "lama"], reg)
    types = [n.type for n in spec.nodes]
    assert types == ["fbcnn", "mask_from_image", "lama"]

    mask_id = next(n.id for n in spec.nodes if n.type == "mask_from_image")
    lama_id = next(n.id for n in spec.nodes if n.type == "lama")
    fbcnn_id = next(n.id for n in spec.nodes if n.type == "fbcnn")

    mask_edge = next(e for e in spec.edges if e.dst == lama_id and e.dst_input == "mask")
    assert mask_edge.src == mask_id
    # The main chain skips over the mask node entirely: fbcnn feeds lama's
    # primary image input directly.
    image_edge = next(e for e in spec.edges if e.dst == lama_id and e.dst_input == "image")
    assert image_edge.src == fbcnn_id


def test_auto_order_respects_an_explicit_mask_source():
    """If the user already picked a mask node, auto-order must not add a
    second one."""
    reg = real_registry()
    spec = auto_order_pipeline(["mask_from_image", "lama"], reg)
    assert [n.type for n in spec.nodes].count("mask_from_image") == 1


def test_auto_order_output_is_a_valid_pipeline():
    """The whole point: what auto-order produces must be directly runnable,
    with no further hand-wiring, through the same validator every pipeline
    goes through before a job is submitted."""
    reg = real_registry()
    spec = auto_order_pipeline(["gfpgan", "lama", "fbcnn", "swinir"], reg)
    parsed = parse_pipeline(spec.to_dict(), reg)
    assert len(parsed.nodes) == 5  # + the auto-inserted mask node
