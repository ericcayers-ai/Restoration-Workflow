"""In-box restoration nodes.

``BUILTIN_NODES`` is what ``NodeRegistry.register_builtins()`` reads. Adding a
model here and adding one from a third-party ``plugins/`` directory go through
exactly the same registration path — that symmetry is the point of the plugin
contract (ARCHITECTURE.md sections 3 and 7), and it's why Phase 6 shouldn't need
to retrofit anything.

Importing this module must stay cheap and torch-free: the API, CLI and analyzer
all start without the ``[inference]`` extra installed, and a node only reports
itself unrunnable when someone actually tries to run it.

DiffBIR and HAT were removed permanently (not Legacy). Former defaults such as
SCUNet, SwinIR, GFPGAN, and BiRefNet remain registered under
``NodeCategory.LEGACY`` for Settings → Legacy only.
"""

from __future__ import annotations

from ..core.types import BaseRestorationNode
from .birefnet import BiRefNetNode
from .codeformer import CodeFormerNode
from .ddcolor import DdColorNode
from .exposure import ExposureCorrectNode
from .face_nodes import GfpganNode, RestoreFormerNode
from .fbcnn import FbcnnNode
from .instructir import InstructIrNode
from .lama import LamaNode
from .masks import BlendNode, MaskFromImageNode
from .old_photos import OldPhotosScratchNode
from .phase4 import (
    FluxFillNode,
    GpenNode,
    OsdFaceNode,
    PowerPaintNode,
    SupirNode,
)
from .realesrgan import RealEsrganNode
from .rmbg2 import Rmbg2Node
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
    FbcnnNode,
    DdColorNode,
    MambaIrNode,
    DarkIrNode,
    InstructIrNode,
    OsdFaceNode,
    Rmbg2Node,
    PowerPaintNode,
    LamaNode,
    BlendNode,
    SupirNode,
    FluxFillNode,
    InstantIrNode,
    DreamClearNode,
    UniRestoreNode,
    RealRestorerNode,
    # --- Legacy (Settings only; hidden from Studio rail / Auto) ---
    ScunetNode,
    SwinIrSrNode,
    SwinIrJpegNode,
    SwinIrDenoiseNode,
    OldPhotosScratchNode,
    GfpganNode,
    RestoreFormerNode,
    CodeFormerNode,
    GpenNode,
    BiRefNetNode,
    MaskFromImageNode,
]

__all__ = [
    "BUILTIN_NODES",
    "BiRefNetNode",
    "BlendNode",
    "CodeFormerNode",
    "DarkIrNode",
    "DdColorNode",
    "DreamClearNode",
    "ExposureCorrectNode",
    "FbcnnNode",
    "FluxFillNode",
    "GpenNode",
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
    "Rmbg2Node",
    "ScunetNode",
    "SupirNode",
    "SwinIrDenoiseNode",
    "SwinIrJpegNode",
    "SwinIrSrNode",
    "UniRestoreNode",
]
