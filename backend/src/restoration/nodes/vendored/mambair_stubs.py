"""Minimal stubs replacing basicsr imports for vendored MambaIRv2."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import torch


def to_2tuple(x: int | tuple[int, ...]) -> tuple[int, ...]:
    if isinstance(x, tuple):
        return x
    return (x, x)


def trunc_normal_(tensor: torch.Tensor, mean: float = 0.0, std: float = 1.0) -> torch.Tensor:
    with torch.no_grad():
        return tensor.normal_(mean, std)


class _Registry:
    def __init__(self) -> None:
        self._store: dict[str, type] = {}

    def register(self) -> Callable[[type], type]:
        def decorator(cls: type) -> type:
            self._store[cls.__name__] = cls
            return cls

        return decorator


ARCH_REGISTRY = _Registry()
