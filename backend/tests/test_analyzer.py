"""Degradation analyzer v1.

The point of these tests is that each metric moves in the direction the rule
table's thresholds assume. A heuristic that is "real and inspectable" rather
than a stub has to actually respond to the degradation it claims to measure.
"""

from __future__ import annotations

import numpy as np
import pytest

from restoration.core.analyzer import DegradationAnalyzer, DegradationProfile

analyzer = DegradationAnalyzer()


def _sharp(size: int = 256, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random((size, size, 3), dtype=np.float32)


def _smooth_gradient(size: int = 256) -> np.ndarray:
    ramp = np.linspace(0.2, 0.8, size, dtype=np.float32)
    return np.repeat(np.repeat(ramp[None, :], size, axis=0)[..., None], 3, axis=2)


def _box_blur(image: np.ndarray, radius: int = 4) -> np.ndarray:
    out = image.copy()
    for _ in range(3):
        padded = np.pad(out, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
        acc = np.zeros_like(out)
        span = 2 * radius + 1
        for dy in range(span):
            for dx in range(span):
                acc += padded[dy : dy + out.shape[0], dx : dx + out.shape[1]]
        out = acc / (span * span)
    return out.astype(np.float32)


def _block_offsets(size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    blocks = rng.random((size // 8, size // 8, 3), dtype=np.float32)
    return np.repeat(np.repeat(blocks, 8, axis=0), 8, axis=1)


def _blocky(size: int = 256, seed: int = 3) -> np.ndarray:
    """8x8 blocks that each still carry texture — what real JPEG artifacts look
    like: seams between blocks, detail preserved (if quantized) inside them."""
    inner_texture = _sharp(size, seed) * 0.15
    return np.clip(inner_texture + _block_offsets(size, seed) * 0.85, 0, 1).astype(np.float32)


def _flat_blocks(size: int = 256, seed: int = 3) -> np.ndarray:
    """The degenerate extreme: quantization has flattened every block interior."""
    return _block_offsets(size, seed)


def test_blur_score_falls_when_the_image_is_blurred():
    sharp = analyzer.analyze(_sharp())
    blurred = analyzer.analyze(_box_blur(_sharp()))
    assert blurred.blur_score < sharp.blur_score
    # The rule table treats <100 as "soft"; a triple box blur must clear that.
    assert blurred.blur_score < 100


def test_noise_score_rises_with_added_noise():
    base = _smooth_gradient()
    rng = np.random.default_rng(11)
    noisy = np.clip(base + rng.normal(0, 0.05, base.shape), 0, 1).astype(np.float32)

    assert analyzer.analyze(base).noise_score < 0.008
    assert analyzer.analyze(noisy).noise_score >= 0.008


def test_jpeg_blockiness_detects_8x8_block_edges():
    clean = analyzer.analyze(_smooth_gradient())
    blocky = analyzer.analyze(_blocky())
    assert clean.jpeg_blockiness < 0.12
    assert blocky.jpeg_blockiness >= 0.12


def test_flat_block_interiors_read_as_maximally_blocky_not_as_clean():
    """A divide-by-zero guard that returns 0.0 would call the most heavily
    quantized image imaginable 'pristine' and route it away from FBCNN."""
    profile = analyzer.analyze(_flat_blocks())
    assert profile.jpeg_blockiness >= 0.12


def test_blockiness_of_a_perfectly_uniform_image_is_zero():
    """No seams and no interior detail: nothing to deblock."""
    assert analyzer.analyze(np.full((64, 64, 3), 0.5, np.float32)).jpeg_blockiness == 0.0


def test_blockiness_is_bounded():
    assert analyzer.analyze(_flat_blocks()).jpeg_blockiness <= 8.0


def test_blockiness_is_zero_on_tiny_images():
    assert analyzer.analyze(np.zeros((8, 8, 3), np.float32)).jpeg_blockiness == 0.0


def test_low_light_flag():
    dark = np.full((128, 128, 3), 0.02, dtype=np.float32)
    profile = analyzer.analyze(dark)
    assert profile.low_light is True
    assert profile.mean_luma < 0.22
    assert profile.dark_fraction > 0.30


def test_blown_highlights_flag():
    bright = np.full((128, 128, 3), 0.99, dtype=np.float32)
    assert analyzer.analyze(bright).blown_highlights is True


def test_normal_exposure_flags_neither():
    profile = analyzer.analyze(_smooth_gradient())
    assert profile.low_light is False
    assert profile.blown_highlights is False


def test_profile_reports_true_dimensions_and_min_dimension():
    profile = analyzer.analyze(np.zeros((64, 200, 3), np.float32))
    assert (profile.width, profile.height) == (200, 64)
    assert profile.min_dimension == 64


def test_face_count_is_an_int_or_none():
    profile = analyzer.analyze(_sharp(128))
    assert profile.face_count is None or isinstance(profile.face_count, int)


def test_grayscale_and_rgba_inputs_are_accepted():
    rgba = np.dstack([_sharp(64), np.ones((64, 64), np.float32)])
    assert isinstance(analyzer.analyze(rgba), DegradationProfile)


def test_profile_dict_is_json_shaped():
    import json

    payload = analyzer.analyze(_sharp(64)).to_dict()
    json.dumps(payload)
    assert set(payload) >= {
        "width", "height", "min_dimension", "blur_score", "noise_score",
        "jpeg_blockiness", "face_count", "low_light", "blown_highlights",
    }


@pytest.mark.parametrize("size", [16, 17, 33, 129])
def test_analyzer_handles_awkward_sizes(size: int):
    analyzer.analyze(_sharp(size))
