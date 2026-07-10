"""Executor: topological order, caching, pin/unload, OOM fallback, cancellation.

Pure logic — no GPU, no weights (ARCHITECTURE.md section 9).
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from restoration.core.errors import (
    JobCancelled,
    NodeExecutionError,
    OutOfMemoryError,
    PipelineValidationError,
)
from restoration.core.executor import (
    EdgeSpec,
    NodeSpec,
    OutputCache,
    PipelineSpec,
    chain_pipeline,
    parse_pipeline,
    sink_nodes,
    topo_sort,
)
from restoration.core.types import NodeStatus, ProgressEvent

from .conftest import OomNode, RecordingNode, make_image


def _spec(nodes, edges) -> PipelineSpec:
    return PipelineSpec(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# validation & topological sort
# ---------------------------------------------------------------------------

def test_topo_sort_is_deterministic_and_respects_edges():
    spec = _spec(
        [NodeSpec("c", "recording"), NodeSpec("a", "recording"), NodeSpec("b", "recording")],
        [EdgeSpec("a", "b"), EdgeSpec("b", "c")],
    )
    assert topo_sort(spec) == ["a", "b", "c"]
    assert topo_sort(spec) == ["a", "b", "c"]  # stable across calls
    assert sink_nodes(spec) == {"c"}


def test_topo_sort_rejects_cycles():
    spec = _spec(
        [NodeSpec("a", "recording"), NodeSpec("b", "recording")],
        [EdgeSpec("a", "b"), EdgeSpec("b", "a")],
    )
    with pytest.raises(PipelineValidationError, match="cycle"):
        topo_sort(spec)


def test_parse_pipeline_rejects_multiple_sinks(registry):
    document = {
        "version": 1,
        "nodes": [{"id": "a", "type": "recording"}, {"id": "b", "type": "recording"}],
        "edges": [],
    }
    with pytest.raises(PipelineValidationError, match="exactly one output"):
        parse_pipeline(document, registry)


@pytest.mark.parametrize(
    "document, message",
    [
        ({"version": 2, "nodes": [{"id": "a", "type": "recording"}]}, "version"),
        ({"version": 1, "nodes": []}, "non-empty"),
        (
            {"version": 1, "nodes": [{"id": "a", "type": "nope"}]},
            "unknown node type",
        ),
        (
            {
                "version": 1,
                "nodes": [{"id": "a", "type": "recording"}, {"id": "a", "type": "recording"}],
            },
            "duplicate node id",
        ),
        (
            {
                "version": 1,
                "nodes": [{"id": "a", "type": "recording"}],
                "edges": [{"from": "a", "to": "ghost"}],
            },
            "unknown node",
        ),
        (
            {
                "version": 1,
                "nodes": [{"id": "a", "type": "recording"}],
                "edges": [{"from": "a", "to": "a"}],
            },
            "to itself",
        ),
    ],
)
def test_parse_pipeline_validation_errors(registry, document, message):
    with pytest.raises(PipelineValidationError, match=message):
        parse_pipeline(document, registry)


def test_parse_pipeline_rejects_double_connected_input(registry):
    document = {
        "version": 1,
        "nodes": [
            {"id": "a", "type": "recording"},
            {"id": "b", "type": "recording"},
            {"id": "c", "type": "merge"},
        ],
        "edges": [
            {"from": "a", "to": "c", "to_input": "image"},
            {"from": "b", "to": "c", "to_input": "image"},
        ],
    }
    with pytest.raises(PipelineValidationError, match="connected twice"):
        parse_pipeline(document, registry)


def test_chain_pipeline_builds_a_linear_graph():
    spec = chain_pipeline(["recording", "scale2x"], {"recording": {"offset": 0.2}})
    assert [n.type for n in spec.nodes] == ["recording", "scale2x"]
    assert spec.nodes[0].params == {"offset": 0.2}
    assert len(spec.edges) == 1
    assert sink_nodes(spec) == {spec.nodes[1].id}


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------

async def test_linear_chain_applies_each_node_in_order(executor):
    image = np.zeros((8, 8, 3), dtype=np.float32)
    spec = chain_pipeline(["recording", "recording"])
    out = await executor.execute(spec, image)
    assert np.allclose(out, 0.2, atol=1e-6)
    assert len(RecordingNode.calls) == 2


async def test_shape_propagates_through_the_dag(executor):
    image = make_image(8, 12)
    spec = chain_pipeline(["scale2x", "scale2x"])
    out = await executor.execute(spec, image)
    assert out.shape == (32, 48, 3)


async def test_branch_and_merge_feeds_the_secondary_input(executor):
    """The reason the executor is a DAG and not a chain (ARCHITECTURE.md s4)."""
    image = np.zeros((4, 4, 3), dtype=np.float32)
    spec = _spec(
        [
            NodeSpec("low", "recording", {"offset": 0.2}),
            NodeSpec("high", "recording", {"offset": 0.6}),
            NodeSpec("m", "merge"),
        ],
        [
            EdgeSpec("low", "m", "image"),
            EdgeSpec("high", "m", "image_b"),
        ],
    )
    out = await executor.execute(spec, image)
    assert np.allclose(out, 0.4, atol=1e-6)


async def test_node_failure_is_wrapped_with_the_node_id(executor):
    spec = chain_pipeline(["boom"])
    with pytest.raises(NodeExecutionError) as excinfo:
        await executor.execute(spec, make_image())
    assert "n0_boom" in str(excinfo.value)
    assert "node exploded" in str(excinfo.value)


async def test_cancellation_raises_job_cancelled(executor):
    cancelled = {"value": False}

    async def cancel_soon():
        await asyncio.sleep(0.03)
        cancelled["value"] = True

    task = asyncio.create_task(cancel_soon())
    with pytest.raises(JobCancelled):
        await executor.execute(
            chain_pipeline(["slow"]), make_image(), is_cancelled=lambda: cancelled["value"]
        )
    await task


# ---------------------------------------------------------------------------
# caching
# ---------------------------------------------------------------------------

async def test_identical_rerun_is_fully_cached(executor):
    image = make_image()
    spec = chain_pipeline(["recording", "recording"])

    await executor.execute(spec, image)
    assert len(RecordingNode.calls) == 2

    events: list[ProgressEvent] = []
    await executor.execute(spec, image, emit=events.append)
    assert len(RecordingNode.calls) == 2, "nothing should have re-run"
    assert all(e.cached for e in events if e.status is NodeStatus.DONE)


async def test_changing_one_param_reruns_only_that_node_and_downstream(executor):
    """Phase 3's 'tweak one parameter, re-run just the affected nodes' criterion."""
    image = make_image()
    first = PipelineSpec(
        nodes=[
            NodeSpec("a", "recording", {"offset": 0.1}),
            NodeSpec("b", "recording", {"offset": 0.1}),
        ],
        edges=[EdgeSpec("a", "b")],
    )
    await executor.execute(first, image)
    RecordingNode.reset()

    second = PipelineSpec(
        nodes=[
            NodeSpec("a", "recording", {"offset": 0.1}),
            NodeSpec("b", "recording", {"offset": 0.3}),  # only b changed
        ],
        edges=[EdgeSpec("a", "b")],
    )
    await executor.execute(second, image)
    assert RecordingNode.calls == ["b"]


async def test_changing_an_upstream_param_invalidates_downstream(executor):
    image = make_image()
    base = PipelineSpec(
        nodes=[
            NodeSpec("a", "recording", {"offset": 0.1}),
            NodeSpec("b", "recording", {"offset": 0.1}),
        ],
        edges=[EdgeSpec("a", "b")],
    )
    await executor.execute(base, image)
    RecordingNode.reset()

    changed = PipelineSpec(
        nodes=[
            NodeSpec("a", "recording", {"offset": 0.4}),  # upstream changed
            NodeSpec("b", "recording", {"offset": 0.1}),
        ],
        edges=[EdgeSpec("a", "b")],
    )
    await executor.execute(changed, image)
    assert RecordingNode.calls == ["a", "b"]


def test_output_cache_is_lru_bounded():
    cache = OutputCache(max_entries=2)
    for i in range(3):
        cache.put(("t", str(i), ()), np.zeros((1, 1, 3), np.float32), str(i))
    assert len(cache) == 2
    assert cache.get(("t", "0", ())) is None
    assert cache.get(("t", "2", ())) is not None


# ---------------------------------------------------------------------------
# pin / unload
# ---------------------------------------------------------------------------

async def test_unpinned_nodes_are_unloaded_after_running(executor):
    await executor.execute(chain_pipeline(["recording"]), make_image(seed=1))
    assert RecordingNode.unloads == ["recording"]


async def test_pinned_nodes_stay_loaded(executor):
    executor.pin("recording")
    assert executor.pinned_types == {"recording"}
    await executor.execute(chain_pipeline(["recording"]), make_image(seed=2))
    assert RecordingNode.unloads == []

    executor.unpin("recording")
    assert executor.pinned_types == set()
    assert RecordingNode.unloads == ["recording"]


# ---------------------------------------------------------------------------
# OOM fallback
# ---------------------------------------------------------------------------

async def test_oom_retries_tiled_when_the_node_supports_it(executor):
    executor.device = "cuda"  # the OOM path only engages off-CPU
    out = await executor.execute(chain_pipeline(["oom_tileable"]), make_image(seed=3))
    assert out.shape == (32, 48, 3)
    assert len(OomNode.attempts) == 2
    assert OomNode.attempts[0].get("tile") in (None, 0)
    assert OomNode.attempts[1]["tile"] == 512


async def test_unrecoverable_oom_suggests_a_lower_tier_node(executor):
    executor.device = "cuda"
    with pytest.raises(OutOfMemoryError) as excinfo:
        await executor.execute(chain_pipeline(["oom_fatal"]), make_image(seed=4))
    error = excinfo.value
    assert error.fallback is not None
    assert "cheap_generative" in error.fallback
    assert "out of memory" in str(error).lower()


async def test_progress_events_cover_every_node(executor):
    events: list[ProgressEvent] = []
    await executor.execute(chain_pipeline(["recording", "scale2x"]), make_image(seed=5),
                           emit=events.append)
    by_node: dict[str, set[NodeStatus]] = {}
    for event in events:
        by_node.setdefault(event.node_id, set()).add(event.status)

    assert len(by_node) == 2
    for statuses in by_node.values():
        assert NodeStatus.QUEUED in statuses
        assert NodeStatus.DONE in statuses
