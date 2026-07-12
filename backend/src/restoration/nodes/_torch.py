"""Shared torch/spandrel plumbing for the in-box model nodes.

Three decisions worth stating explicitly, because they are load-bearing:

*   **Weights are deserialized safely.** Checkpoints are read with
    ``torch.load(..., weights_only=True)`` and handed to spandrel as a plain
    state dict; we never call ``ModelLoader.load_from_file``, which permits
    arbitrary pickle globals. These files are multi-hundred-megabyte blobs
    fetched over the network, and loading one must not be able to execute code.
    The WeightManager's checksum gate (ARCHITECTURE.md section 6) is the other
    half of this; neither is sufficient alone.

*   **Architectures come from spandrel's MAIN_REGISTRY only.** That package is
    MIT-licensed and deliberately excludes the non-commercial architectures
    (CodeFormer, MAT, ...), which upstream ships separately in
    ``spandrel_extra_arches``. Depending on the main package alone is a
    licensing guardrail, not an accident (MODEL_STACK.md "Licensing tiers").

*   **Inference is blocking and stays off the event loop.** Everything here is
    synchronous; nodes call it through ``asyncio.to_thread`` so the WebSocket
    progress stream keeps ticking during a long convolution.

Nothing in this module imports torch at import time — the engine, API, CLI and
analyzer all work with the ``[inference]`` extra absent, and nodes report
themselves unrunnable instead of the app failing to start.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from ..core.errors import InferenceUnavailableError, NodeExecutionError
from ..core.types import BaseRestorationNode, ImageArray, RunContext

# A tile smaller than this costs more in per-tile overhead than it saves in peak
# memory, and starves the network of context.
_MIN_TILE = 64
# Context margin around each tile. Wide enough to cover the receptive field of
# the convolutional restoration models in the box; a margin narrower than that
# is what makes tiled output show seams.
_DEFAULT_TILE_PAD = 32


_extra_arches_installed = False


def _install_extra_arches() -> None:
    """Register spandrel_extra_arches' architectures (CodeFormer, DDColor, ...) into
    spandrel's main registry, once. The extra-arches *package* is MIT-licensed loader
    code, distinct from any individual model's own weight license (checked per-node,
    same as every other license gate in this app) — installing it costs nothing and
    unlocks nothing on its own; a node still needs its weights downloaded and, if
    non-permissive, acknowledged. Best-effort: a plugin or minimal install without the
    package simply can't load an extra-arch checkpoint, which surfaces as this node's
    own "not a checkpoint this node can load" error, not a startup failure."""
    global _extra_arches_installed
    if _extra_arches_installed:
        return
    try:
        import spandrel_extra_arches  # noqa: PLC0415

        spandrel_extra_arches.install(ignore_duplicates=True)
    except ImportError:
        pass
    _extra_arches_installed = True


def require_torch(node_id: str) -> tuple[Any, Any]:
    """Import torch + spandrel, or raise the engine's typed 'no inference' error."""
    try:
        import spandrel  # noqa: PLC0415
        import torch  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise InferenceUnavailableError(node_id) from exc
    _install_extra_arches()
    return torch, spandrel


def inference_available() -> bool:
    try:
        import spandrel  # noqa: F401, PLC0415
        import torch  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


StateDictTransform = Callable[[dict], dict]


def read_state_dict(node_id: str, path: str | Path) -> dict:
    """Read a checkpoint into a state dict without ever unpickling arbitrary objects.

    ``.safetensors`` cannot express anything but tensors, so it is read directly.
    Everything else goes through ``torch.load(weights_only=True)``, which refuses
    checkpoints carrying pickled objects — a Lightning checkpoint that embeds its
    trainer callbacks will fail here, and that refusal is the feature.
    """
    torch, _ = require_torch(node_id)
    path = Path(path)

    if path.suffix == ".safetensors":
        try:
            from safetensors.torch import load_file  # noqa: PLC0415

            return load_file(str(path), device="cpu")
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise InferenceUnavailableError(node_id) from exc
        except Exception as exc:
            raise NodeExecutionError(
                node_id, f"could not read weight file '{path.name}': {exc}"
            ) from exc

    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise NodeExecutionError(
            node_id,
            f"could not safely read weight file '{path.name}': {exc}",
        ) from exc


def load_descriptor(
    node_id: str,
    path: str | Path,
    *,
    transform: StateDictTransform | None = None,
) -> Any:
    """Load a checkpoint into a spandrel ModelDescriptor, safely.

    ``transform`` rewrites the raw state dict before spandrel sees it, for
    checkpoints whose key layout doesn't match what spandrel's architecture
    detector expects (see restoreformer.py and lama.py for real instances).
    """
    _, spandrel = require_torch(node_id)
    path = Path(path)
    state_dict = read_state_dict(node_id, path)

    if transform is not None:
        state_dict = transform(state_dict)

    try:
        return spandrel.ModelLoader().load_from_state_dict(state_dict)
    except Exception as exc:
        raise NodeExecutionError(
            node_id,
            f"'{path.name}' is not a checkpoint this node can load "
            f"(spandrel: {type(exc).__name__}: {exc})",
        ) from exc


def descriptor_scale(descriptor: Any) -> int:
    """Output/input size ratio. Masked (inpainting) descriptors have no scale."""
    return int(getattr(descriptor, "scale", 1) or 1)


# ---------------------------------------------------------------------------
# numpy <-> torch, with alpha preserved across the model call
# ---------------------------------------------------------------------------

def split_alpha(image: ImageArray) -> tuple[ImageArray, ImageArray | None]:
    if image.ndim == 3 and image.shape[2] == 4:
        return np.ascontiguousarray(image[..., :3]), np.ascontiguousarray(image[..., 3])
    return image, None


def merge_alpha(rgb: ImageArray, alpha: ImageArray | None) -> ImageArray:
    """Re-attach alpha, resampling it if the model changed the spatial size."""
    if alpha is None:
        return rgb
    if alpha.shape[:2] != rgb.shape[:2]:
        from PIL import Image  # noqa: PLC0415

        resized = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8)).resize(
            (rgb.shape[1], rgb.shape[0]), Image.BICUBIC
        )
        alpha = np.asarray(resized, dtype=np.float32) / 255.0
    return np.concatenate([rgb, alpha[..., None]], axis=2)


def to_tensor(torch: Any, image: ImageArray, device: str, dtype: Any) -> Any:
    """HWC float32 [0,1] -> (1, C, H, W) on device."""
    arr = image if image.ndim == 3 else image[..., None]
    t = torch.from_numpy(np.ascontiguousarray(arr)).permute(2, 0, 1).unsqueeze(0)
    return t.to(device=device, dtype=dtype)


def to_numpy(tensor: Any) -> ImageArray:
    """(1, C, H, W) -> HWC float32 [0,1]."""
    arr = tensor.detach().float().clamp_(0.0, 1.0).squeeze(0).permute(1, 2, 0).cpu().numpy()
    return np.ascontiguousarray(arr, dtype=np.float32)


# ---------------------------------------------------------------------------
# Inference: whole-image and tiled
# ---------------------------------------------------------------------------

def _call(descriptor: Any, x: Any, mask: Any | None) -> Any:
    return descriptor(x) if mask is None else descriptor(x, mask)


def _infer_whole(descriptor: Any, x: Any, mask: Any | None) -> Any:
    """Pad up to the architecture's size requirements, run, crop back."""
    import torch.nn.functional as F  # noqa: PLC0415, N812

    h, w = x.shape[-2:]
    req = getattr(descriptor, "size_requirements", None)
    pad_w, pad_h = req.get_padding(w, h) if req is not None else (0, 0)
    if pad_w or pad_h:
        # 'replicate' rather than 'reflect': reflect requires padding < the
        # dimension being padded, which a 512-minimum face model violates on a
        # small crop.
        x = F.pad(x, (0, pad_w, 0, pad_h), mode="replicate")
        if mask is not None:
            mask = F.pad(mask, (0, pad_w, 0, pad_h), mode="replicate")

    out = _call(descriptor, x, mask)
    s = descriptor_scale(descriptor)
    return out[..., : h * s, : w * s]


def _infer_tiled(
    descriptor: Any,
    x: Any,
    mask: Any | None,
    tile: int,
    pad: int,
    on_progress: Callable[[float], None] | None,
    check_cancel: Callable[[], None] | None,
) -> Any:
    """Run the model tile by tile, giving each tile real context and keeping only
    its centre.

    Output tiles do **not** overlap. Each one is produced from an input region
    grown by ``pad`` pixels on every side (clamped at the image border), and only
    the centre — the part that corresponds to the output tile — is written out.
    The padding exists so that pixels near a tile's edge are computed with the
    neighbouring content actually present, rather than against the implicit zero
    padding of the network's own convolutions.

    The alternative — overlapping tiles cross-faded together — averages two
    equally-wrong edge predictions instead of discarding them, and leaves a
    visible seam wherever the receptive field is wider than the overlap. This is
    the scheme Real-ESRGAN's own tiled inference uses, for the same reason.
    """
    import torch  # noqa: PLC0415

    _, _, h, w = x.shape
    s = descriptor_scale(descriptor)
    out_c = int(getattr(descriptor, "output_channels", x.shape[1]))
    out = torch.zeros((1, out_c, h * s, w * s), dtype=x.dtype, device=x.device)

    ys = list(range(0, h, tile))
    xs = list(range(0, w, tile))
    total = len(ys) * len(xs)

    for i, y0 in enumerate(ys):
        for j, x0 in enumerate(xs):
            if check_cancel is not None:
                check_cancel()
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)

            # Input region: the output tile plus its context margin.
            py0, py1 = max(0, y0 - pad), min(h, y1 + pad)
            px0, px1 = max(0, x0 - pad), min(w, x1 + pad)

            patch = x[..., py0:py1, px0:px1]
            mpatch = None if mask is None else mask[..., py0:py1, px0:px1]
            result = _infer_whole(descriptor, patch, mpatch)

            # Discard the margin: keep only what maps to [y0:y1, x0:x1].
            top, left = (y0 - py0) * s, (x0 - px0) * s
            height, width = (y1 - y0) * s, (x1 - x0) * s
            out[..., y0 * s : y1 * s, x0 * s : x1 * s] = result[
                ..., top : top + height, left : left + width
            ]
            if on_progress is not None:
                on_progress((i * len(xs) + j + 1) / total)

    return out


def infer(
    descriptor: Any,
    x: Any,
    *,
    mask: Any | None = None,
    tile: int = 0,
    pad: int = _DEFAULT_TILE_PAD,
    on_progress: Callable[[float], None] | None = None,
    check_cancel: Callable[[], None] | None = None,
) -> Any:
    """Run a spandrel descriptor, tiling when asked to (or when told to by the
    executor's OOM fallback, which re-runs the node with ``tile`` set).

    A tile request is honoured by clamping it up to ``_MIN_TILE`` rather than
    silently ignored: a caller asking to tile is a caller who would otherwise run
    out of memory, and quietly running the whole image instead would OOM them.
    """
    if tile:
        tile = max(int(tile), _MIN_TILE)
        pad = max(0, int(pad))
        h, w = x.shape[-2:]
        if h > tile or w > tile:
            return _infer_tiled(descriptor, x, mask, tile, pad, on_progress, check_cancel)
    if on_progress is not None:
        on_progress(1.0)
    return _infer_whole(descriptor, x, mask)


# ---------------------------------------------------------------------------
# Base class for the spandrel-backed nodes
# ---------------------------------------------------------------------------

class SpandrelNode(BaseRestorationNode):
    """A node whose weights spandrel can load and whose call is image -> image.

    Subclasses declare ``weight_manifest`` and implement ``weight_filename``;
    the descriptor is loaded lazily on first run and cached on the instance, so
    a pinned node ("keep loaded" in Studio Mode) keeps its weights resident
    while an unpinned one is dropped by the executor immediately after it
    completes (ARCHITECTURE.md section 4).
    """

    supports_tiling = True
    uses_gpu = True

    #: Rewrites the raw state dict before spandrel's architecture detection.
    state_dict_transform: StateDictTransform | None = None

    def __init__(self) -> None:
        self._descriptors: dict[str, Any] = {}

    # -- weights ------------------------------------------------------------

    def weight_filename(self, params: dict[str, Any]) -> str:
        """Which file in the manifest this call needs (RealESRGAN picks by scale)."""
        if len(self.weight_manifest) != 1:
            raise NotImplementedError(
                f"{type(self).__name__} has {len(self.weight_manifest)} weight files "
                f"and must override weight_filename()"
            )
        return self.weight_manifest[0].filename

    def descriptor(self, ctx: RunContext, params: dict[str, Any]) -> Any:
        filename = self.weight_filename(params)
        cached = self._descriptors.get(filename)
        if cached is not None:
            return cached

        if ctx.weights_dir is None:
            raise NodeExecutionError(self.id, "no weights directory was provided")
        torch, _ = require_torch(self.id)
        desc = load_descriptor(
            self.id, Path(ctx.weights_dir) / filename, transform=self.state_dict_transform
        )
        desc.to(self._torch_device(torch, ctx.device)).eval()
        self._descriptors[filename] = desc
        return desc

    @staticmethod
    def _torch_device(torch: Any, device: str) -> Any:
        return torch.device(device)

    def unload(self) -> None:
        if not self._descriptors:
            return
        self._descriptors.clear()
        try:
            import torch  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            return
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # -- run ----------------------------------------------------------------

    async def run(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        import asyncio  # noqa: PLC0415

        return await asyncio.to_thread(self.run_sync, image, params, ctx)

    def run_sync(
        self, image: ImageArray, params: dict[str, Any], ctx: RunContext
    ) -> ImageArray:
        raise NotImplementedError

    # -- helper used by the straightforward image -> image nodes -------------

    def _run_descriptor(
        self,
        image: ImageArray,
        params: dict[str, Any],
        ctx: RunContext,
        *,
        mask: ImageArray | None = None,
    ) -> ImageArray:
        torch, _ = require_torch(self.id)
        desc = self.descriptor(ctx, params)
        rgb, alpha = split_alpha(image)

        x = to_tensor(torch, rgb, str(desc.device), desc.dtype)
        m = None
        if mask is not None:
            m = to_tensor(torch, mask[..., None] if mask.ndim == 2 else mask,
                          str(desc.device), desc.dtype)

        out = infer(
            desc,
            x,
            mask=m,
            tile=int(params.get("tile") or 0),
            pad=int(params.get("tile_pad") or _DEFAULT_TILE_PAD),
            on_progress=ctx.report_progress,
            check_cancel=ctx.check_cancelled,
        )
        return merge_alpha(to_numpy(out), alpha)
