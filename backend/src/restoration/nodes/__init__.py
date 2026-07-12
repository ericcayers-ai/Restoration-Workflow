"""In-box restoration nodes.

``BUILTIN_NODES`` is what ``NodeRegistry.register_builtins()`` reads. Adding a
model here and adding one from a third-party ``plugins/`` directory go through
exactly the same registration path — that symmetry is the point of the plugin
contract (ARCHITECTURE.md sections 3 and 7), and it's why Phase 6 shouldn't need
to retrofit anything.

Importing this module must stay cheap and torch-free: the API, CLI and analyzer
all start without the ``[inference]`` extra installed, and a node only reports
itself unrunnable when someone actually tries to run it.
"""

from __future__ import annotations

from ..core.types import BaseRestorationNode
from .codeformer import CodeFormerNode
from .face_nodes import GfpganNode, RestoreFormerNode
from .fbcnn import FbcnnNode
from .lama import LamaNode
from .masks import BlendNode, MaskFromImageNode
from .realesrgan import RealEsrganNode
from .scunet import ScunetNode
from .swinir import SwinIrDenoiseNode, SwinIrJpegNode, SwinIrSrNode

BUILTIN_NODES: list[type[BaseRestorationNode]] = [
    RealEsrganNode,
    SwinIrSrNode,
    FbcnnNode,
    SwinIrJpegNode,
    ScunetNode,
    SwinIrDenoiseNode,
    GfpganNode,
    RestoreFormerNode,
    CodeFormerNode,
    LamaNode,
    MaskFromImageNode,
    BlendNode,
]

__all__ = [
    "BUILTIN_NODES",
    "BlendNode",
    "CodeFormerNode",
    "FbcnnNode",
    "GfpganNode",
    "LamaNode",
    "MaskFromImageNode",
    "RealEsrganNode",
    "RestoreFormerNode",
    "ScunetNode",
    "SwinIrDenoiseNode",
    "SwinIrJpegNode",
    "SwinIrSrNode",
]
