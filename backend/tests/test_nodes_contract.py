"""Contract tests for the in-box nodes (ARCHITECTURE.md section 9).

Every node is checked for the things the rest of the app relies on without
asking: a stable id, a licence, a JSON-Schema param block the Inspector can
render, and a weight manifest with exactly one resolvable source per file.

The weightless nodes (``mask_from_image``, ``blend``) are additionally run for
real on synthetic images. The model-backed nodes are *not* run here: doing so
needs ~1.3GB of checkpoints and is the job of the separate
``-m weights`` smoke test, not of CI on every push.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from restoration.core.errors import NodeExecutionError
from restoration.core.registry import NodeRegistry
from restoration.core.types import (
    ImageMeta,
    LicenseKind,
    NodeCategory,
    RunContext,
    VramTier,
)
from restoration.nodes import BUILTIN_NODES

ALL_IDS = [cls.id for cls in BUILTIN_NODES]


@pytest.fixture
def ctx() -> RunContext:
    return RunContext(job_id="t", node_id="n", device="cpu")


def _image(h=16, w=16, c=3, value=0.5) -> np.ndarray:
    return np.full((h, w, c), value, dtype=np.float32)


# ---------------------------------------------------------------------------
# the contract every node meets
# ---------------------------------------------------------------------------

def test_node_ids_are_unique_and_non_empty():
    assert len(ALL_IDS) == len(set(ALL_IDS))
    assert all(ALL_IDS)


@pytest.mark.parametrize("cls", BUILTIN_NODES, ids=ALL_IDS)
def test_node_metadata_is_well_formed(cls):
    node = cls()
    assert isinstance(node.category, NodeCategory)
    assert isinstance(node.vram_tier, VramTier)
    assert isinstance(node.license.kind, LicenseKind)
    assert node.display_name
    assert node.description


@pytest.mark.parametrize("cls", BUILTIN_NODES, ids=ALL_IDS)
def test_param_schema_is_a_renderable_json_schema(cls):
    schema = cls().param_schema
    assert schema["type"] == "object"
    assert isinstance(schema["properties"], dict)
    json.dumps(schema)  # the Inspector receives this over HTTP

    for name, spec in schema["properties"].items():
        assert "type" in spec, f"{cls.id}.{name} has no type"
        assert "title" in spec, f"{cls.id}.{name} has no title"


@pytest.mark.parametrize("cls", BUILTIN_NODES, ids=ALL_IDS)
def test_default_params_come_from_the_schema(cls):
    node = cls()
    defaults = node.default_params()
    for name, spec in node.param_schema["properties"].items():
        if "default" in spec:
            assert defaults[name] == spec["default"]


@pytest.mark.parametrize("cls", BUILTIN_NODES, ids=ALL_IDS)
def test_weight_manifest_entries_have_exactly_one_source(cls):
    for weight in cls().weight_manifest:
        from_url = weight.url is not None
        from_hf = weight.hf_repo_id is not None and weight.hf_filename is not None
        assert from_url != from_hf
        assert weight.size_bytes > 0
        if weight.sha256 is not None:
            assert len(weight.sha256) == 64
        elif cls.id not in _GATED_BUILTIN_IDS and cls.id not in _TOFU_PHASE4_IDS:
            pytest.fail(
                f"{cls.id}.{weight.filename} must pin sha256 or be listed in _TOFU_PHASE4_IDS"
            )


_TOFU_PHASE4_IDS = {
    "diffbir",
    "supir",
    "flux_fill",
    "osdface",
    "darkir",
    "instantir",
    "dreamclear",
    "unirestore",
    "realrestorer",
}


@pytest.mark.parametrize("cls", BUILTIN_NODES, ids=ALL_IDS)
def test_describe_is_json_serializable(cls):
    json.dumps(cls().describe())


_GATED_BUILTIN_IDS = {
    "codeformer",
    "gpen",
    "osdface",
    "supir",
    "flux_fill",
    "darkir",
    "realrestorer",
}


def test_permissively_licensed_nodes_need_no_acknowledgement():
    """Every builtin not on the explicit gated list must be permissive and
    unacknowledged-by-default; the acknowledgement gate is opt-in, not a default
    a permissive node should ever need. Default-pipeline safety (the rule table
    never routing to a gated node) is enforced separately by
    RuleTable.validate() against the real registry, tested in test_rules.py."""
    for cls in BUILTIN_NODES:
        if cls.id in _GATED_BUILTIN_IDS:
            continue
        assert cls.license.kind is LicenseKind.PERMISSIVE, cls.id
        assert cls.license.requires_acknowledgement is False


def test_gated_builtin_nodes_are_actually_gated():
    """A node on the gated list had better actually require acknowledgement —
    otherwise its non-permissive weights would download with no gate at all."""
    by_id = {cls.id: cls for cls in BUILTIN_NODES}
    for node_id in _GATED_BUILTIN_IDS:
        cls = by_id[node_id]
        assert cls.license.kind is not LicenseKind.PERMISSIVE, node_id
        assert cls.license.requires_acknowledgement is True, node_id


def test_weightless_nodes_declare_no_weights():
    registry = NodeRegistry()
    registry.register_builtins()
    for node_id in ("blend", "mask_from_image"):
        node = registry.create(node_id)
        assert node.weight_manifest == []
        assert node.uses_gpu is False


def test_face_nodes_do_not_claim_tiling():
    """A face model only ever sees one 512x512 crop; there is nothing to tile,
    and claiming otherwise would make the executor's OOM fallback lie."""
    from restoration.nodes import GfpganNode, RestoreFormerNode

    assert GfpganNode.supports_tiling is False
    assert RestoreFormerNode.supports_tiling is False


def test_realesrgan_selects_its_checkpoint_by_scale():
    from restoration.nodes import RealEsrganNode

    node = RealEsrganNode()
    assert node.weight_filename({"scale": 2}) == "RealESRGAN_x2plus.pth"
    assert node.weight_filename({"scale": 4}) == "RealESRGAN_x4plus.pth"
    assert node.weight_filename({}) == "RealESRGAN_x4plus.pth"


def test_face_nodes_ship_the_shared_detector():
    from restoration.nodes import CodeFormerNode, GfpganNode, RestoreFormerNode
    from restoration.nodes._faces import YUNET_FILENAME

    for cls in (GfpganNode, RestoreFormerNode, CodeFormerNode):
        names = {w.filename for w in cls.weight_manifest}
        assert YUNET_FILENAME in names
        assert cls.model_filename in names


def test_restoreformer_transform_strips_the_vqvae_prefix():
    """Guards the real incompatibility found between the shipped checkpoint and
    spandrel's architecture detection."""
    from restoration.nodes.face_nodes import _restoreformer_state_dict

    raw = {
        "state_dict": {
            "vqvae.encoder.conv_in.weight": 1,
            "vqvae.quantize.utility_counter": 2,
            "loss.discriminator.weight": 3,
        }
    }
    assert _restoreformer_state_dict(raw) == {"encoder.conv_in.weight": 1}


def test_lama_transform_keeps_only_the_generator():
    from restoration.nodes.lama import _generator_only

    raw = {"generator.model.1.weight": 1, "discriminator.0.weight": 2}
    assert _generator_only(raw) == {"generator.model.1.weight": 1}


# ---------------------------------------------------------------------------
# the weightless nodes actually run
# ---------------------------------------------------------------------------

async def test_mask_from_alpha_marks_transparent_pixels(ctx):
    from restoration.nodes import MaskFromImageNode

    rgba = np.ones((8, 8, 4), dtype=np.float32)
    rgba[2:4, 2:4, 3] = 0.0  # a transparent hole

    mask = await MaskFromImageNode().run(rgba, {"source": "alpha", "threshold": 0.5}, ctx)
    assert mask.shape == (8, 8, 3)
    assert mask[2, 2, 0] == 1.0
    assert mask[0, 0, 0] == 0.0


async def test_mask_from_alpha_errors_without_an_alpha_channel(ctx):
    from restoration.nodes import MaskFromImageNode

    with pytest.raises(NodeExecutionError, match="no alpha channel"):
        await MaskFromImageNode().run(_image(), {"source": "alpha"}, ctx)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_old_photos_scratch_runs(ctx):
    from restoration.nodes import OldPhotosScratchNode

    out = await OldPhotosScratchNode().run(_image(), {}, ctx)
    assert out.shape == (16, 16, 3)


async def test_mask_from_luma_thresholds_brightness(ctx):
    from restoration.nodes import MaskFromImageNode

    image = np.zeros((4, 4, 3), dtype=np.float32)
    image[0, 0] = 1.0
    mask = await MaskFromImageNode().run(image, {"source": "luma", "threshold": 0.5}, ctx)
    assert mask[0, 0, 0] == 1.0
    assert mask[1, 1, 0] == 0.0


async def test_mask_invert_and_dilate(ctx):
    from restoration.nodes import MaskFromImageNode

    image = np.zeros((7, 7, 3), dtype=np.float32)
    image[3, 3] = 1.0

    mask = await MaskFromImageNode().run(
        image, {"source": "luma", "threshold": 0.5, "dilate": 1}, ctx
    )
    assert mask[2, 2, 0] == 1.0  # grew diagonally
    assert mask[0, 0, 0] == 0.0

    inverted = await MaskFromImageNode().run(
        image, {"source": "luma", "threshold": 0.5, "invert": True}, ctx
    )
    assert inverted[3, 3, 0] == 0.0
    assert inverted[0, 0, 0] == 1.0


async def test_blend_mixes_two_branches(ctx):
    from restoration.nodes import BlendNode

    a, b = _image(value=0.0), _image(value=1.0)
    ctx.inputs = {"image": a, "image_b": b}

    out = await BlendNode().run(a, {"alpha": 0.25}, ctx)
    assert np.allclose(out, 0.25)


@pytest.mark.parametrize("mode, expected", [("lighten", 1.0), ("darken", 0.0)])
async def test_blend_modes(ctx, mode, expected):
    from restoration.nodes import BlendNode

    a, b = _image(value=0.0), _image(value=1.0)
    ctx.inputs = {"image": a, "image_b": b}
    out = await BlendNode().run(a, {"mode": mode}, ctx)
    assert np.allclose(out, expected)


async def test_blend_without_a_second_branch_explains_itself(ctx):
    from restoration.nodes import BlendNode

    with pytest.raises(NodeExecutionError, match="image_b"):
        await BlendNode().run(_image(), {}, ctx)


async def test_blend_rejects_mismatched_resolutions(ctx):
    from restoration.nodes import BlendNode

    ctx.inputs = {"image": _image(16, 16), "image_b": _image(8, 8)}
    with pytest.raises(NodeExecutionError, match="same resolution"):
        await BlendNode().run(_image(16, 16), {}, ctx)


async def test_lama_without_a_mask_explains_itself(ctx):
    from restoration.nodes import LamaNode

    with pytest.raises(NodeExecutionError, match="mask"):
        await LamaNode().run_sync(_image(), {}, ctx)


def test_lama_mask_shape_mismatch_is_reported():
    from restoration.nodes.lama import _as_mask

    with pytest.raises(NodeExecutionError, match="must be produced from the same image"):
        _as_mask(np.zeros((4, 4, 3), np.float32), (8, 8), "lama")


def test_face_nodes_support_only_colour_images():
    from restoration.nodes import GfpganNode

    node = GfpganNode()
    assert node.supports(ImageMeta(width=64, height=64, channels=3)) is True
    assert node.supports(ImageMeta(width=64, height=64, channels=1)) is False


# ---------------------------------------------------------------------------
# the generic spandrel wrapper (nodes/wrappers.py) — the "easy path" for a new
# paper/model wrapping any spandrel-supported architecture in a single call
# ---------------------------------------------------------------------------

def test_wrapper_factory_produces_a_registrable_node_class():
    from restoration.core.ordering import STAGE_UPSCALE
    from restoration.core.types import LicenseInfo, LicenseKind, VramTier, WeightFile
    from restoration.nodes.wrappers import spandrel_image_node

    NewModelNode = spandrel_image_node(
        id="new_model",
        display_name="New Model",
        description="A hypothetical future model.",
        category=NodeCategory.REGRESSION,
        stage=STAGE_UPSCALE,
        vram_tier=VramTier.MID,
        license=LicenseInfo("Apache-2.0", LicenseKind.PERMISSIVE, "https://example.com"),
        weights=[
            WeightFile(
                filename="w.pth", size_bytes=16, sha256="0" * 64,
                url="https://example.invalid/w.pth",
            )
        ],
    )

    registry = NodeRegistry()
    registry.register(NewModelNode)  # the same path a plugin manifest uses
    node = registry.create("new_model")

    described = node.describe()
    json.dumps(described)  # must be wire-serializable, same as every built-in
    assert described["id"] == "new_model"
    assert described["pipeline_stage"] == STAGE_UPSCALE
    assert described["license"]["kind"] == "permissive"
    # Tiling knobs are added automatically; the caller only named model params.
    assert "tile" in described["param_schema"]["properties"]
    assert "tile_pad" in described["param_schema"]["properties"]


def test_wrapper_factory_adds_model_specific_params_alongside_tiling():
    from restoration.core.types import LicenseInfo, LicenseKind, VramTier, WeightFile
    from restoration.nodes.wrappers import spandrel_image_node

    NoiseModelNode = spandrel_image_node(
        id="noise_model",
        display_name="Noise Model",
        description="Takes a noise-level knob.",
        category=NodeCategory.REGRESSION,
        vram_tier=VramTier.LOW,
        license=LicenseInfo("MIT", LicenseKind.PERMISSIVE, "https://example.com"),
        weights=[WeightFile(filename="w.pth", size_bytes=16, sha256="0" * 64,
                             url="https://example.invalid/w.pth")],
        params={"noise_level": {"type": "integer", "default": 25, "title": "Noise level"}},
    )
    node = NoiseModelNode()
    assert set(node.param_schema["properties"]) == {"noise_level", "tile", "tile_pad"}
    assert node.default_params()["noise_level"] == 25


def test_wrapper_factory_can_disable_tiling():
    from restoration.core.types import LicenseInfo, LicenseKind, VramTier, WeightFile
    from restoration.nodes.wrappers import spandrel_image_node

    FaceLikeNode = spandrel_image_node(
        id="face_like",
        display_name="Face Like",
        description="A fixed-crop model with nothing to tile.",
        category=NodeCategory.FACE,
        vram_tier=VramTier.LOW,
        license=LicenseInfo("MIT", LicenseKind.PERMISSIVE, "https://example.com"),
        weights=[WeightFile(filename="w.pth", size_bytes=16, sha256="0" * 64,
                             url="https://example.invalid/w.pth")],
        supports_tiling=False,
    )
    node = FaceLikeNode()
    assert node.supports_tiling is False
    assert node.param_schema["properties"] == {}
