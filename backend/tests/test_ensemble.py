"""InstructIR prompt library + ensemble conductor."""

from __future__ import annotations

import numpy as np

from restoration.core.analyzer import DegradationAnalyzer
from restoration.core.ensemble import build_guided_ensemble, prompt_library_summary
from restoration.core.highlight import soft_blend_masked
from restoration.core.instruction import list_prompt_presets, prompt_by_id, prompt_for_workflow
from restoration.core.registry import NodeRegistry


def test_prompt_library_has_enough_presets():
    presets = list_prompt_presets()
    assert len(presets) >= 16
    for p in presets:
        assert p["id"] and p["title"] and p["instruction"]


def test_prompt_pairs_with_blown_highlight_workflow():
    preset = prompt_for_workflow("Blown Highlight Rescue")
    assert preset is not None
    assert preset["id"] == "blown_highlight_rescue"


def test_prompt_library_summary_shape():
    summary = prompt_library_summary()
    assert summary["count"] == len(summary["presets"])


def test_ensemble_instruct_only():
    reg = NodeRegistry()
    reg.register_builtins()
    plan = build_guided_ensemble(
        None,
        registry=reg,
        prompt_preset_id="instruct_only_general",
        mode="instruct_only",
    )
    assert plan.chain == ["instructir"]
    assert plan.specialist_pipeline is not None


def test_ensemble_highlight_hint_includes_specialists():
    reg = NodeRegistry()
    reg.register_builtins()
    bright = np.full((128, 128, 3), 0.99, dtype=np.float32)
    profile = DegradationAnalyzer().analyze(bright)
    plan = build_guided_ensemble(
        profile,
        registry=reg,
        prompt_preset_id="blown_highlight_rescue",
        mode="guide_and_finish",
    )
    assert "exposure_correct" in plan.chain or "instructir" in plan.chain
    assert plan.instruction
    reasons = " ".join(r["reason"] for r in plan.reasons)
    assert "instructir" in plan.chain or "Master" in reasons or "highlight" in reasons.lower()


def test_soft_blend_masked_preserves_unmasked():
    original = np.zeros((32, 32, 3), dtype=np.float32)
    restored = np.ones((32, 32, 3), dtype=np.float32)
    mask = np.zeros((32, 32), dtype=np.float32)
    mask[8:24, 8:24] = 1.0
    out = soft_blend_masked(original, restored, mask, feather=0.0)
    assert out[0, 0, 0] == 0.0
    assert out[16, 16, 0] == 1.0


def test_prompt_by_id_roundtrip():
    assert prompt_by_id("jpeg_cleanup")["title"] == "JPEG cleanup"
