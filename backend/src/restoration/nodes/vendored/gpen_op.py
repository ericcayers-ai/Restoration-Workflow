"""Pure-PyTorch stand-ins for GPEN's fused CUDA ops (yangxy/GPEN, CVPR 2021).

The upstream ``op.py`` compiles custom kernels; this module keeps GPEN runnable
on CPU-only installs and avoids a compile step in CI.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class FusedLeakyReLU(nn.Module):
    def __init__(self, channel: int, negative_slope: float = 0.2, scale: float = 2**0.5):
        super().__init__()
        self.bias = nn.Parameter(torch.zeros(channel))
        self.negative_slope = negative_slope
        self.scale = scale

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return fused_leaky_relu(x, self.bias, self.negative_slope, self.scale)


def fused_leaky_relu(
    x: torch.Tensor,
    bias: torch.Tensor,
    negative_slope: float = 0.2,
    scale: float = 2**0.5,
) -> torch.Tensor:
    return F.leaky_relu(x + bias.view(1, -1, 1, 1), negative_slope=negative_slope) * scale


def upfirdn2d(
    input: torch.Tensor,
    kernel: torch.Tensor,
    up: int = 1,
    down: int = 1,
    pad: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> torch.Tensor:
    """Bilinear upsample / pad / downsample — sufficient for inference."""
    out = input
    if up > 1:
        out = F.interpolate(out, scale_factor=up, mode="bilinear", align_corners=False)
    if any(pad):
        out = F.pad(out, (pad[0], pad[1], pad[2], pad[3]))
    if down > 1:
        out = F.avg_pool2d(out, down)
    return out
