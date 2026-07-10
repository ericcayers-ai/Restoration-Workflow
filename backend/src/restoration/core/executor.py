"""Pipeline executor: a general topological-sort DAG runner
(ARCHITECTURE.md section 4), cloned conceptually from ComfyUI's execution
engine without its license or UI.

Pipeline JSON (version 1):

    {
      "version": 1,
      "nodes": [{"id": "a", "type": "realesrgan", "params": {...},
                 "pinned": false}],
      "edges": [{"from": "a", "to": "b", "to_input": "image"}]
    }

Semantics:
- Node ids are pipeline-instance ids; ``type`` is a registered node type.
- Any node with no incoming "image" edge receives the pipeline's input image.
- The pipeline's result is the output of the single sink node (exactly one
  node with no outgoing edges); multi-sink graphs are a validation error.
- ``to_input`` defaults to "image" (the primary input). Other names (e.g.
  "image_b" for blend, "mask" for inpainting) land in RunContext.inputs.

Execution rules implemented here:
- Topological order; independent branches run concurrently, but GPU-bound
  node execution is serialized by a GPU semaphore.
- Per-node output caching keyed by (node type, params hash, upstream output
  hashes) — changing one parameter re-runs only that node and downstream.
- Nodes are unloaded from (V)RAM immediately after completing unless pinned.
- CUDA OOM is caught; if the node supports tiling we retry tiled, otherwise
  the error carries a concrete lower-tier fallback suggestion.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import (
    JobCancelled,
    NodeExecutionError,
    OutOfMemoryError,
    PipelineValidationError,
)
from .registry import NodeRegistry
from .types import (
    BaseRestorationNode,
    EventCallback,
    ImageArray,
    ImageMeta,
    NodeStatus,
    ProgressEvent,
    RunContext,
    array_hash,
    params_hash,
)
from .weights import WeightManager

PIPELINE_VERSION = 1
PRIMARY_INPUT = "image"


# ---------------------------------------------------------------------------
# Pipeline spec parsing & validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeSpec:
    id: str
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    pinned: bool = False


@dataclass(frozen=True)
class EdgeSpec:
    src: str
    dst: str
    dst_input: str = PRIMARY_INPUT


@dataclass
class PipelineSpec:
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    version: int = PIPELINE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "nodes": [
                {"id": n.id, "type": n.type, "params": n.params, "pinned": n.pinned}
                for n in self.nodes
            ],
            "edges": [
                {"from": e.src, "to": e.dst, "to_input": e.dst_input}
                for e in self.edges
            ],
        }


def chain_pipeline(
    node_types: list[str], params: dict[str, dict] | None = None
) -> PipelineSpec:
    """Build a linear pipeline from a list of node types (analyzer/CLI helper)."""
    params = params or {}
    nodes, edges = [], []
    for i, node_type in enumerate(node_types):
        nid = f"n{i}_{node_type}"
        nodes.append(NodeSpec(id=nid, type=node_type, params=params.get(node_type, {})))
        if i > 0:
            edges.append(EdgeSpec(src=nodes[i - 1].id, dst=nid))
    return PipelineSpec(nodes=nodes, edges=edges)


def parse_pipeline(data: dict[str, Any], registry: NodeRegistry) -> PipelineSpec:
    if not isinstance(data, dict):
        raise PipelineValidationError("pipeline must be a JSON object")
    version = data.get("version", PIPELINE_VERSION)
    if version != PIPELINE_VERSION:
        raise PipelineValidationError(f"unsupported pipeline version {version!r}")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise PipelineValidationError("pipeline needs a non-empty 'nodes' list")

    nodes: list[NodeSpec] = []
    seen: set[str] = set()
    for raw in raw_nodes:
        if not isinstance(raw, dict) or "id" not in raw or "type" not in raw:
            raise PipelineValidationError("each node needs 'id' and 'type'")
        nid = str(raw["id"])
        if nid in seen:
            raise PipelineValidationError(f"duplicate node id '{nid}'")
        seen.add(nid)
        ntype = str(raw["type"])
        if ntype not in registry:
            raise PipelineValidationError(f"unknown node type '{ntype}'")
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            raise PipelineValidationError(f"node '{nid}': params must be an object")
        nodes.append(NodeSpec(id=nid, type=ntype, params=params,
                              pinned=bool(raw.get("pinned", False))))

    edges: list[EdgeSpec] = []
    edge_keys: set[tuple[str, str]] = set()
    for raw in data.get("edges", []):
        if not isinstance(raw, dict) or "from" not in raw or "to" not in raw:
            raise PipelineValidationError("each edge needs 'from' and 'to'")
        e = EdgeSpec(src=str(raw["from"]), dst=str(raw["to"]),
                     dst_input=str(raw.get("to_input", PRIMARY_INPUT)))
        for endpoint in (e.src, e.dst):
            if endpoint not in seen:
                raise PipelineValidationError(f"edge references unknown node '{endpoint}'")
        if e.src == e.dst:
            raise PipelineValidationError(f"edge from '{e.src}' to itself")
        key = (e.dst, e.dst_input)
        if key in edge_keys:
            raise PipelineValidationError(
                f"node '{e.dst}' input '{e.dst_input}' is connected twice"
            )
        edge_keys.add(key)
        edges.append(e)

    spec = PipelineSpec(nodes=nodes, edges=edges, version=version)
    topo_sort(spec)  # raises on cycles
    sinks = sink_nodes(spec)
    if len(sinks) != 1:
        raise PipelineValidationError(
            f"pipeline must have exactly one output (sink) node, found {len(sinks)}: "
            f"{sorted(sinks)}"
        )
    return spec


def topo_sort(spec: PipelineSpec) -> list[str]:
    """Kahn's algorithm; deterministic order; raises on cycles."""
    indegree = {n.id: 0 for n in spec.nodes}
    downstream: dict[str, list[str]] = defaultdict(list)
    for e in spec.edges:
        indegree[e.dst] += 1
        downstream[e.src].append(e.dst)

    ready = sorted(nid for nid, deg in indegree.items() if deg == 0)
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in sorted(downstream[nid]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort()
    if len(order) != len(spec.nodes):
        cyclic = sorted(set(indegree) - set(order))
        raise PipelineValidationError(f"pipeline contains a cycle involving {cyclic}")
    return order


def sink_nodes(spec: PipelineSpec) -> set[str]:
    has_out = {e.src for e in spec.edges}
    return {n.id for n in spec.nodes} - has_out


# ---------------------------------------------------------------------------
# Output cache
# ---------------------------------------------------------------------------

class OutputCache:
    """LRU cache of node outputs keyed by
    (node type, params hash, sorted upstream output hashes)."""

    def __init__(self, max_entries: int = 64):
        self._max = max_entries
        self._store: OrderedDict[tuple, tuple[ImageArray, str]] = OrderedDict()

    @staticmethod
    def key(node_type: str, params: dict, upstream: dict[str, str]) -> tuple:
        return (
            node_type,
            params_hash(params),
            tuple(sorted(upstream.items())),
        )

    def get(self, key: tuple) -> tuple[ImageArray, str] | None:
        hit = self._store.get(key)
        if hit is not None:
            self._store.move_to_end(key)
        return hit

    def put(self, key: tuple, image: ImageArray, digest: str) -> None:
        self._store[key] = (image, digest)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

def _is_oom(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in ("OutOfMemoryError", "CudaError") and "torch" in type(exc).__module__:
        return True
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()


_OOM_TILE_SIZE = 512


class PipelineExecutor:
    """Runs PipelineSpecs. One instance per backend process; holds the GPU
    semaphore and the shared output cache so Studio Mode re-runs stay warm."""

    def __init__(
        self,
        registry: NodeRegistry,
        weights: WeightManager,
        *,
        device: str = "cpu",
        gpu_slots: int = 1,
        cache: OutputCache | None = None,
    ):
        self.registry = registry
        self.weights = weights
        self.device = device
        # Raised above 1 only if multi-GPU is detected and the user opts in.
        self._gpu_lock = asyncio.Semaphore(gpu_slots)
        self.cache = cache if cache is not None else OutputCache()
        # Nodes the user pinned, kept loaded across runs: instance per type.
        self._pinned_loaded: dict[str, BaseRestorationNode] = {}

    # -- public API ---------------------------------------------------------------

    async def execute(
        self,
        spec: PipelineSpec,
        input_image: ImageArray,
        *,
        job_id: str = "local",
        emit: EventCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        preview_sink: Callable[[ImageArray], str | None] | None = None,
    ) -> ImageArray:
        emit = emit or (lambda _e: None)
        order = topo_sort(spec)
        by_id = {n.id: n for n in spec.nodes}
        incoming: dict[str, list[EdgeSpec]] = defaultdict(list)
        for e in spec.edges:
            incoming[e.dst].append(e)

        for nid in order:
            emit(ProgressEvent(node_id=nid, status=NodeStatus.QUEUED))

        outputs: dict[str, ImageArray] = {}
        hashes: dict[str, str] = {}
        input_digest = array_hash(input_image)

        remaining = dict.fromkeys(order)
        done: set[str] = set()

        while remaining:
            if is_cancelled and is_cancelled():
                raise JobCancelled(f"job {job_id} was cancelled")
            wave = [
                nid for nid in remaining
                if all(e.src in done for e in incoming[nid])
            ]
            if not wave:  # unreachable given topo_sort validation
                raise PipelineValidationError("pipeline deadlocked (cycle?)")

            results = await asyncio.gather(*[
                self._run_node(
                    by_id[nid], incoming[nid], outputs, hashes,
                    input_image, input_digest,
                    job_id=job_id, emit=emit,
                    is_cancelled=is_cancelled, preview_sink=preview_sink,
                )
                for nid in wave
            ])
            for nid, (out, digest) in zip(wave, results, strict=True):
                outputs[nid] = out
                hashes[nid] = digest
                done.add(nid)
                del remaining[nid]

        (sink,) = sink_nodes(spec)
        return outputs[sink]

    def pin(self, node_type: str) -> None:
        """Keep a node's weights loaded across runs ('keep loaded' toggle)."""
        if node_type not in self._pinned_loaded:
            self._pinned_loaded[node_type] = self.registry.create(node_type)

    def unpin(self, node_type: str) -> None:
        node = self._pinned_loaded.pop(node_type, None)
        if node is not None:
            node.unload()

    @property
    def pinned_types(self) -> set[str]:
        return set(self._pinned_loaded)

    # -- internals ---------------------------------------------------------------

    def _gather_inputs(
        self,
        edges: list[EdgeSpec],
        outputs: dict[str, ImageArray],
        hashes: dict[str, str],
        input_image: ImageArray,
        input_digest: str,
    ) -> tuple[ImageArray, dict[str, ImageArray], dict[str, str]]:
        inputs: dict[str, ImageArray] = {}
        upstream_hashes: dict[str, str] = {}
        for e in edges:
            inputs[e.dst_input] = outputs[e.src]
            upstream_hashes[e.dst_input] = hashes[e.src]
        if PRIMARY_INPUT not in inputs:
            inputs[PRIMARY_INPUT] = input_image
            upstream_hashes[PRIMARY_INPUT] = input_digest
        return inputs[PRIMARY_INPUT], inputs, upstream_hashes

    async def _run_node(
        self,
        node_spec: NodeSpec,
        edges: list[EdgeSpec],
        outputs: dict[str, ImageArray],
        hashes: dict[str, str],
        input_image: ImageArray,
        input_digest: str,
        *,
        job_id: str,
        emit: EventCallback,
        is_cancelled: Callable[[], bool] | None,
        preview_sink: Callable[[ImageArray], str | None] | None,
    ) -> tuple[ImageArray, str]:
        primary, inputs, upstream = self._gather_inputs(
            edges, outputs, hashes, input_image, input_digest
        )

        key = OutputCache.key(node_spec.type, node_spec.params, upstream)
        cached = self.cache.get(key)
        if cached is not None:
            emit(ProgressEvent(node_id=node_spec.id, status=NodeStatus.DONE,
                               progress=1.0, cached=True))
            return cached

        pinned = node_spec.pinned or node_spec.type in self._pinned_loaded
        node = self._pinned_loaded.get(node_spec.type) or self.registry.create(node_spec.type)
        if node_spec.pinned:
            self._pinned_loaded[node_spec.type] = node

        if not node.supports(ImageMeta.from_array(primary)):
            raise NodeExecutionError(
                node_spec.id,
                f"'{node_spec.type}' does not support this input image",
            )

        weights_dir: str | None = None
        if node.weight_manifest:
            emit(ProgressEvent(node_id=node_spec.id, status=NodeStatus.LOADING_WEIGHTS))
            weights_dir = str(self.weights.ensure_installed(node))

        ctx = RunContext(
            job_id=job_id,
            node_id=node_spec.id,
            device=self.device,
            weights_dir=weights_dir,
            inputs=inputs,
            _emit=emit,
            _is_cancelled=is_cancelled,
            _preview_sink=preview_sink,
        )
        params = {**node.default_params(), **node_spec.params}

        emit(ProgressEvent(node_id=node_spec.id, status=NodeStatus.RUNNING))
        try:
            out = await self._run_with_oom_fallback(node, node_spec, primary, params, ctx)
        except JobCancelled:
            raise
        except NodeExecutionError as exc:
            emit(ProgressEvent(node_id=node_spec.id, status=NodeStatus.ERROR,
                               message=str(exc)))
            raise
        except Exception as exc:
            emit(ProgressEvent(node_id=node_spec.id, status=NodeStatus.ERROR,
                               message=str(exc)))
            raise NodeExecutionError(node_spec.id, str(exc)) from exc
        finally:
            if not pinned:
                node.unload()

        digest = array_hash(out)
        self.cache.put(key, out, digest)
        emit(ProgressEvent(node_id=node_spec.id, status=NodeStatus.DONE, progress=1.0))
        return out, digest

    async def _run_with_oom_fallback(
        self,
        node: BaseRestorationNode,
        node_spec: NodeSpec,
        image: ImageArray,
        params: dict[str, Any],
        ctx: RunContext,
    ) -> ImageArray:
        async def _locked_run(p: dict[str, Any]) -> ImageArray:
            if node.uses_gpu and ctx.device != "cpu":
                async with self._gpu_lock:
                    await node.load(ctx)
                    return await node.run(image, p, ctx)
            await node.load(ctx)
            return await node.run(image, p, ctx)

        try:
            return await _locked_run(params)
        except Exception as exc:
            if not _is_oom(exc):
                raise
            # OOM path: concrete fallback, never a crashed run (ARCH. section 4).
            if node.supports_tiling and not params.get("tile"):
                ctx.report_progress(
                    0.0, f"GPU ran out of memory; retrying in {_OOM_TILE_SIZE}px tiles"
                )
                node.unload()
                try:
                    return await _locked_run({**params, "tile": _OOM_TILE_SIZE})
                except Exception as exc2:
                    if not _is_oom(exc2):
                        raise
                    exc = exc2
            fallback = self.registry.fallback_for(node)
            raise OutOfMemoryError(
                node_spec.id,
                "GPU out of memory"
                + (" even with tiled processing" if node.supports_tiling else ""),
                fallback=(
                    f"try the lower-VRAM '{fallback}' node for this category"
                    if fallback else "reduce input resolution and retry"
                ),
            ) from exc
