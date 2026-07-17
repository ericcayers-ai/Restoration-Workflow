"""Quality tiers: model-choice + tile-size adjustment on top of an already-
routed chain (ROADMAP.md Phase 4.5.4). Uses the real registry — the whole
point is that these swaps target real node ids and real supports_tiling
flags, not a fake stand-in graph.
"""

from __future__ import annotations

from restoration.core.hardware import GpuDevice, HardwareInfo
from restoration.core.quality import QualityTier, apply_quality_tier, tile_size_for
from restoration.core.registry import NodeRegistry


def real_registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register_builtins()
    return reg


def cpu_hardware() -> HardwareInfo:
    return HardwareInfo(backend="cpu", torch_available=True)


def gpu_hardware(vram_mb: int) -> HardwareInfo:
    return HardwareInfo(
        backend="cuda",
        devices=(GpuDevice(index=0, name="test-gpu", total_vram_mb=vram_mb),),
        torch_available=True,
    )


def test_tile_size_grows_with_vram_and_shrinks_with_tier():
    assert tile_size_for(QualityTier.DRAFT, cpu_hardware()) < tile_size_for(
        QualityTier.HIGH, cpu_hardware()
    )
    assert tile_size_for(QualityTier.DRAFT, cpu_hardware()) < tile_size_for(
        QualityTier.DRAFT, gpu_hardware(24 * 1024)
    )


def test_high_tier_prefers_mambair_when_its_weights_are_installed():
    reg = real_registry()
    chain, params = apply_quality_tier(
        ["realesrgan"], {"realesrgan": {"scale": 4}}, QualityTier.HIGH,
        cpu_hardware(), reg, quality_upscale_ready=True,
    )
    assert chain == ["mambair"]
    assert "realesrgan" not in params
    assert "tile" in params["mambair"]


def test_high_tier_keeps_the_fast_model_when_quality_weights_are_missing():
    reg = real_registry()
    chain, _ = apply_quality_tier(
        ["realesrgan"], {}, QualityTier.HIGH, cpu_hardware(), reg,
        quality_upscale_ready=False,
    )
    assert chain == ["realesrgan"]


def test_draft_tier_swaps_mambair_for_the_faster_realesrgan():
    reg = real_registry()
    chain, params = apply_quality_tier(
        ["mambair"], {"mambair": {"scale": 4}}, QualityTier.DRAFT, cpu_hardware(), reg,
    )
    assert chain == ["realesrgan"]
    assert "mambair" not in params


def test_draft_tier_does_not_swap_face_nodes():
    """Face rail is OSDFace-only (gated overlay); draft no longer drops faces."""
    reg = real_registry()
    chain, _ = apply_quality_tier(
        ["osdface"], {}, QualityTier.DRAFT, cpu_hardware(), reg,
    )
    assert chain == ["osdface"]


def test_high_tier_does_not_invent_a_second_face_pass():
    reg = real_registry()
    chain, _ = apply_quality_tier(
        ["osdface"], {}, QualityTier.HIGH, cpu_hardware(), reg,
        quality_face_ready=True,
    )
    assert chain == ["osdface"]


def test_high_tier_does_not_add_a_face_pass_to_a_photo_with_no_face_stage():
    """Never invents a stage the rule table didn't already decide the image
    needs — quality tiers only change *which* model fills an existing role."""
    reg = real_registry()
    chain, _ = apply_quality_tier(
        ["fbcnn"], {}, QualityTier.HIGH, cpu_hardware(), reg, quality_face_ready=True,
    )
    assert chain == ["fbcnn"]


def test_balanced_tier_leaves_the_chain_untouched_besides_tile_size():
    reg = real_registry()
    chain, params = apply_quality_tier(
        ["realesrgan", "osdface"], {"realesrgan": {"scale": 4}}, QualityTier.BALANCED,
        cpu_hardware(), reg,
    )
    assert chain == ["realesrgan", "osdface"]
    assert "tile" in params["realesrgan"]
    assert "osdface" not in params or "tile" not in params.get("osdface", {})


def test_non_tileable_nodes_never_get_a_tile_param():
    reg = real_registry()
    _, params = apply_quality_tier(
        ["osdface"], {}, QualityTier.HIGH, cpu_hardware(), reg,
    )
    assert "tile" not in params.get("osdface", {})
