"""Tiled inference: the executor's OOM fallback depends on this being correct.

Driven with a stand-in descriptor rather than a real checkpoint, so the geometry
(placement, cropping, scale, borders) is asserted exactly. An identity model must
tile to an identity result — if it doesn't, the tiling is wrong regardless of how
plausible a real model's output looks.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="tiling is part of the [inference] extra")

from restoration.nodes._torch import _MIN_TILE, infer  # noqa: E402


class SizeReq:
    def __init__(self, minimum: int = 0, multiple_of: int = 1) -> None:
        self.minimum, self.multiple_of = minimum, multiple_of

    def get_padding(self, width: int, height: int) -> tuple[int, int]:
        def ceil_to(v: int) -> int:
            v = max(v, self.minimum)
            rem = v % self.multiple_of
            return v if rem == 0 else v + self.multiple_of - rem

        return ceil_to(width) - width, ceil_to(height) - height


class FakeDescriptor:
    """Records the input regions it is shown; upsamples by ``scale``."""

    def __init__(self, scale: int = 1, size_requirements: SizeReq | None = None) -> None:
        self.scale = scale
        self.output_channels = 3
        self.size_requirements = size_requirements or SizeReq()
        self.seen: list[tuple[int, int]] = []

    def __call__(self, x, mask=None):
        self.seen.append((x.shape[-2], x.shape[-1]))
        if self.scale == 1:
            return x.clone()
        return torch.nn.functional.interpolate(x, scale_factor=self.scale, mode="nearest")


def _ramp(h: int, w: int) -> torch.Tensor:
    """A non-repeating field, so a misplaced tile can't accidentally match."""
    ys = torch.arange(h, dtype=torch.float32)[:, None]
    xs = torch.arange(w, dtype=torch.float32)[None, :]
    plane = (ys * w + xs) / float(h * w)
    return plane.expand(3, h, w).unsqueeze(0).clone()


@pytest.mark.parametrize("tile", [64, 96, 128])
@pytest.mark.parametrize("pad", [0, 16, 32])
def test_identity_model_tiles_to_an_identity_result(tile, pad):
    x = _ramp(200, 173)  # deliberately not a multiple of any tile size
    out = infer(FakeDescriptor(scale=1), x, tile=tile, pad=pad)
    assert out.shape == x.shape
    assert torch.allclose(out, x, atol=1e-6)


@pytest.mark.parametrize("scale", [2, 4])
def test_tiling_matches_whole_image_for_a_scaling_model(scale):
    x = _ramp(150, 130)
    whole = infer(FakeDescriptor(scale=scale), x, tile=0)
    tiled = infer(FakeDescriptor(scale=scale), x, tile=64, pad=16)
    assert tiled.shape == whole.shape == (1, 3, 150 * scale, 130 * scale)
    assert torch.allclose(tiled, whole, atol=1e-6)


def test_tiles_are_given_context_and_the_margin_is_discarded():
    descriptor = FakeDescriptor(scale=1)
    x = _ramp(128, 128)
    infer(descriptor, x, tile=64, pad=16)

    # 2x2 output tiles. Interior tiles see 64 + 16 context on the inward sides.
    assert len(descriptor.seen) == 4
    assert descriptor.seen[0] == (80, 80)   # top-left: padded right & bottom only
    assert descriptor.seen[3] == (80, 80)   # bottom-right: padded left & top only


def test_no_padding_means_each_tile_sees_exactly_its_own_pixels():
    descriptor = FakeDescriptor(scale=1)
    infer(descriptor, _ramp(128, 128), tile=64, pad=0)
    assert descriptor.seen == [(64, 64)] * 4


def test_a_tile_request_is_clamped_up_not_silently_ignored():
    """Asking to tile at 8px must still tile: the caller is avoiding an OOM."""
    descriptor = FakeDescriptor(scale=1)
    infer(descriptor, _ramp(200, 200), tile=8, pad=0)
    assert len(descriptor.seen) > 1
    assert descriptor.seen[0] == (_MIN_TILE, _MIN_TILE)


def test_an_image_smaller_than_the_tile_runs_whole():
    descriptor = FakeDescriptor(scale=1)
    infer(descriptor, _ramp(64, 64), tile=128)
    assert descriptor.seen == [(64, 64)]


def test_tile_zero_disables_tiling():
    descriptor = FakeDescriptor(scale=1)
    infer(descriptor, _ramp(300, 300), tile=0)
    assert descriptor.seen == [(300, 300)]


def test_size_requirements_are_padded_and_cropped_back():
    descriptor = FakeDescriptor(scale=1, size_requirements=SizeReq(minimum=64, multiple_of=8))
    x = _ramp(30, 45)
    out = infer(descriptor, x, tile=0)
    assert descriptor.seen == [(64, 64)]      # padded up to the minimum
    assert out.shape == x.shape               # and cropped back down
    assert torch.allclose(out, x, atol=1e-6)


def test_progress_reaches_one_and_is_monotonic():
    seen: list[float] = []
    infer(FakeDescriptor(scale=1), _ramp(200, 200), tile=64, on_progress=seen.append)
    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(1.0)


def test_cancellation_propagates_out_of_the_tile_loop():
    calls = {"n": 0}

    def check() -> None:
        calls["n"] += 1
        if calls["n"] > 2:
            raise KeyboardInterrupt("cancelled")

    with pytest.raises(KeyboardInterrupt):
        infer(FakeDescriptor(scale=1), _ramp(256, 256), tile=64, check_cancel=check)


def test_tiled_output_has_no_seam_for_an_identity_model():
    """The old cross-fade scheme left a measurable ridge here; padding-and-crop
    must not."""
    x = _ramp(192, 192)
    out = infer(FakeDescriptor(scale=1), x, tile=64, pad=16)
    error = (out - x).abs().numpy()
    for boundary in (64, 128):
        assert error[..., boundary - 1 : boundary + 1].max() == pytest.approx(0.0, abs=1e-6)


def test_masked_descriptor_receives_the_same_tile_region():
    class MaskedFake(FakeDescriptor):
        def __call__(self, x, mask=None):
            assert mask is not None
            assert mask.shape[-2:] == x.shape[-2:]
            return super().__call__(x, None)

    x = _ramp(128, 128)
    mask = torch.zeros((1, 1, 128, 128))
    out = infer(MaskedFake(scale=1), x, mask=mask, tile=64, pad=16)
    assert torch.allclose(out, x, atol=1e-6)


def test_numpy_round_trip_preserves_values():
    from restoration.nodes._torch import to_numpy, to_tensor

    image = np.random.default_rng(0).random((16, 24, 3)).astype(np.float32)
    restored = to_numpy(to_tensor(torch, image, "cpu", torch.float32))
    assert np.allclose(restored, image, atol=1e-6)


def test_alpha_is_split_and_reattached_across_a_scale_change():
    from restoration.nodes._torch import merge_alpha, split_alpha

    rgba = np.random.default_rng(1).random((8, 8, 4)).astype(np.float32)
    rgb, alpha = split_alpha(rgba)
    assert rgb.shape == (8, 8, 3) and alpha.shape == (8, 8)

    upscaled_rgb = np.repeat(np.repeat(rgb, 2, 0), 2, 1)
    merged = merge_alpha(upscaled_rgb, alpha)
    assert merged.shape == (16, 16, 4)


def test_merge_alpha_is_a_noop_without_alpha():
    from restoration.nodes._torch import merge_alpha

    rgb = np.zeros((4, 4, 3), np.float32)
    assert merge_alpha(rgb, None) is rgb
