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
from .birefnet import BiRefNetNode
from .codeformer import CodeFormerNode
from .ddcolor import DdColorNode
from .exposure import ExposureCorrectNode
from .face_nodes import GfpganNode, RestoreFormerNode
from .fbcnn import FbcnnNode
from .hat import HatNode
from .instructir import InstructIrNode
from .lama import LamaNode
from .masks import BlendNode, MaskFromImageNode
from .old_photos import OldPhotosScratchNode
from .phase4 import (
    DiffBirNode,
    FluxFillNode,
    GpenNode,
    OsdFaceNode,
    PowerPaintNode,
    SupirNode,
)
from .realesrgan import RealEsrganNode
from .scunet import ScunetNode
from .stretch import (
    DarkIrNode,
    DreamClearNode,
    InstantIrNode,
    MambaIrNode,
    RealRestorerNode,
    UniRestoreNode,
)
from .swinir import SwinIrDenoiseNode, SwinIrJpegNode, SwinIrSrNode

BUILTIN_NODES: list[type[BaseRestorationNode]] = [
    ExposureCorrectNode,
    RealEsrganNode,
    HatNode,
    SwinIrSrNode,
    FbcnnNode,
    SwinIrJpegNode,
    ScunetNode,
    SwinIrDenoiseNode,
    DdColorNode,
    DiffBirNode,
    MambaIrNode,
    DarkIrNode,
    InstructIrNode,
    GfpganNode,
    RestoreFormerNode,
    CodeFormerNode,
    GpenNode,
    OsdFaceNode,
    BiRefNetNode,
    PowerPaintNode,
    LamaNode,
    MaskFromImageNode,
    BlendNode,
    OldPhotosScratchNode,
    SupirNode,
    FluxFillNode,
    InstantIrNode,
    DreamClearNode,
    UniRestoreNode,
    RealRestorerNode,
]

__all__ = [
    "BUILTIN_NODES",
    "BiRefNetNode",
    "BlendNode",
    "CodeFormerNode",
    "DarkIrNode",
    "DdColorNode",
    "DiffBirNode",
    "DreamClearNode",
    "ExposureCorrectNode",
    "FbcnnNode",
    "FluxFillNode",
    "GpenNode",
    "HatNode",
    "InstantIrNode",
    "InstructIrNode",
    "LamaNode",
    "MambaIrNode",
    "MaskFromImageNode",
    "OldPhotosScratchNode",
    "OsdFaceNode",
    "PowerPaintNode",
    "RealEsrganNode",
    "RealRestorerNode",
    "RestoreFormerNode",
    "ScunetNode",
    "SupirNode",
    "SwinIrDenoiseNode",
    "SwinIrJpegNode",
    "SwinIrSrNode",
    "UniRestoreNode",
]
