"""Rule table: DegradationProfile -> default node chain.

The licence guardrail (`validate`) is tested as hard as the routing is: the
Simple Mode default pipeline must never depend on a non-commercial model, and
that is enforced in code, not only in a document (ROADMAP.md guardrails).
"""

from __future__ import annotations

import pytest

from restoration.core.analyzer import DegradationProfile
from restoration.core.errors import PipelineValidationError
from restoration.core.registry import NodeRegistry
from restoration.core.rules import RuleTable, Stage


def profile(**overrides) -> DegradationProfile:
    """A clean, large, face-free image; override one axis per test."""
    base = dict(
        width=2000,
        height=2000,
        blur_score=500.0,
        noise_score=0.001,
        jpeg_blockiness=0.0,
        mean_luma=0.5,
        dark_fraction=0.0,
        bright_fraction=0.0,
        face_count=0,
        low_light=False,
        blown_highlights=False,
    )
    base.update(overrides)
    return DegradationProfile(**base)


@pytest.fixture
def table() -> RuleTable:
    return RuleTable.load_default()


@pytest.fixture
def real_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_builtins()
    return registry


# ---------------------------------------------------------------------------
# the shipped table
# ---------------------------------------------------------------------------

def test_default_table_validates_against_the_real_registry(table, real_registry):
    """Catches a rule table that references a node that doesn't exist, or one
    whose licence would drag the default path into non-commercial territory."""
    table.validate(real_registry)


def test_clean_large_image_falls_back_to_the_default_chain(table):
    decision = table.route(profile())
    assert decision.chain == ["realesrgan"]
    assert "no specific degradation" in decision.reasons[0]["reason"]


def test_small_image_routes_to_the_quality_upscaler(table):
    """Below 800px the default reaches for SwinIR's transformer 4x SR, the
    highest-quality upscale in the permissive stack."""
    decision = table.route(profile(width=800, height=600))
    assert decision.chain == ["swinir"]
    assert decision.params["swinir"] == {"scale": 4}


def test_moderate_resolution_routes_to_the_fast_upscaler(table):
    """Between 800 and 1600px the default uses the faster general 4x upscaler,
    and the two upscale bands never both fire (no double upscale)."""
    decision = table.route(profile(width=1200, height=1000))
    assert decision.chain == ["realesrgan"]
    assert decision.params["realesrgan"] == {"scale": 4}


def test_noise_routes_to_the_blind_denoiser(table):
    """Visible noise adds SCUNet's blind real-world denoise stage; on an already
    large image that is the whole chain (nothing to upscale)."""
    decision = table.route(profile(noise_score=0.02))
    assert decision.chain == ["scunet"]
    assert decision.params["scunet"] == {"variant": "gan"}


def test_jpeg_artifacts_run_before_the_upscaler(table):
    """Order matters: cleaning blocks first stops the upscaler amplifying them."""
    decision = table.route(profile(width=800, height=600, jpeg_blockiness=0.3))
    assert decision.chain == ["fbcnn", "swinir"]


def test_faces_append_the_face_nodes_after_the_upscaler(table):
    decision = table.route(profile(width=800, height=600, face_count=2))
    assert decision.chain == ["swinir", "gfpgan"]


def test_soft_faces_add_the_quality_face_node(table):
    decision = table.route(profile(width=800, height=600, face_count=1, blur_score=40.0))
    assert decision.chain == ["swinir", "gfpgan", "restoreformer"]


def test_compound_degradation_chains_every_stage(table):
    """The SOTA default at full stretch: deblock -> denoise -> quality upscale ->
    fast face -> quality face, five permissive models in one adaptive chain."""
    decision = table.route(
        profile(
            width=600,
            height=400,
            jpeg_blockiness=0.4,
            noise_score=0.02,
            face_count=1,
            blur_score=20.0,
        )
    )
    assert decision.chain == ["fbcnn", "scunet", "swinir", "gfpgan", "restoreformer"]
    assert len(decision.reasons) == 5


def test_absent_face_detector_never_routes_to_a_face_node(table):
    """A null metric means 'no evidence', not 'condition satisfied'."""
    decision = table.route(profile(width=800, height=600, face_count=None))
    assert "gfpgan" not in decision.chain
    assert "restoreformer" not in decision.chain


def test_routing_decision_is_serializable(table):
    import json

    json.dumps(table.route(profile()).to_dict())


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_validate_rejects_a_non_permissive_node(real_registry):
    from .conftest import NonCommercialNode

    real_registry.register(NonCommercialNode)
    bad = RuleTable(
        {
            "version": 1,
            "fallback_chain": ["realesrgan"],
            "stages": [{"node": "gated", "when": {}}],
        }
    )
    with pytest.raises(PipelineValidationError, match="not permissive"):
        bad.validate(real_registry)


def test_validate_rejects_an_unknown_node(real_registry):
    bad = RuleTable({"version": 1, "fallback_chain": ["ghost"], "stages": []})
    with pytest.raises(PipelineValidationError, match="unknown node type"):
        bad.validate(real_registry)


def test_validate_checks_the_fallback_chain_too(real_registry):
    from .conftest import NonCommercialNode

    real_registry.register(NonCommercialNode)
    bad = RuleTable({"version": 1, "fallback_chain": ["gated"], "stages": []})
    with pytest.raises(PipelineValidationError, match="not permissive"):
        bad.validate(real_registry)


def test_unsupported_version_is_rejected():
    with pytest.raises(PipelineValidationError, match="version"):
        RuleTable({"version": 99, "fallback_chain": ["x"]})


def test_empty_fallback_chain_is_rejected():
    with pytest.raises(PipelineValidationError, match="fallback_chain"):
        RuleTable({"version": 1, "stages": []})


def test_unknown_operator_is_rejected():
    stage = Stage(node="x", when={"blur_score": {"approximately": 5}})
    with pytest.raises(PipelineValidationError, match="unknown operator"):
        stage.matches({"blur_score": 5})


def test_a_stage_never_appends_the_same_node_twice():
    table = RuleTable(
        {
            "version": 1,
            "fallback_chain": ["realesrgan"],
            "stages": [
                {"node": "realesrgan", "when": {"blur_score": {"lt": 1000}}},
                {"node": "realesrgan", "when": {"noise_score": {"lt": 1000}}},
            ],
        }
    )
    assert table.route(profile()).chain == ["realesrgan"]


@pytest.mark.parametrize(
    "condition, value, expected",
    [
        ({"gte": 5}, 5, True),
        ({"gt": 5}, 5, False),
        ({"lte": 5}, 5, True),
        ({"lt": 5}, 5, False),
        ({"eq": 5}, 5, True),
        ({"is": True}, True, True),
        ({"is": False}, True, False),
    ],
)
def test_condition_operators(condition, value, expected):
    assert Stage(node="x", when={"metric": condition}).matches({"metric": value}) is expected
