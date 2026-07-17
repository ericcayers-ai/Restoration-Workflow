"""Tests for the built-in workflow presets (v0.6 catalog)."""

from __future__ import annotations

from pathlib import Path

import pytest

from restoration.builtin_presets import (
    BUILTIN_PRESET_VERSION,
    builtin_preset_names,
    seed_builtin_presets,
)
from restoration.core.executor import parse_pipeline
from restoration.core.registry import NodeRegistry
from restoration.presets import PresetStore


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register_builtins()
    return reg


def test_builtin_preset_definitions_cover_all_lanes():
    names = builtin_preset_names()
    assert len(names) >= 28
    assert len(set(names)) == len(names)
    for required in (
        "Colorize BW",
        "Blown Highlight Rescue",
        "InstructIR Solo",
        "SUPIR Maximum",
        "RMBG Matte",
        "Night DarkIR",
    ):
        assert required in names
    assert "DiffBIR Polish" not in names


def test_seed_builtin_presets_writes_catalog(tmp_path: Path, registry: NodeRegistry):
    store = PresetStore(tmp_path)
    count = seed_builtin_presets(store, registry)
    assert count == len(builtin_preset_names())
    assert len(store.list()) == len(builtin_preset_names())
    # Idempotent without version bump
    assert seed_builtin_presets(store, registry) == 0
    # Force refresh rewrites
    rewritten = seed_builtin_presets(
        store, registry, force_version=BUILTIN_PRESET_VERSION + 1
    )
    assert rewritten == len(builtin_preset_names())


def test_each_builtin_preset_is_valid_pipeline(tmp_path: Path, registry: NodeRegistry):
    store = PresetStore(tmp_path)
    seed_builtin_presets(store, registry)
    for preset in store.list():
        spec = parse_pipeline(preset.pipeline, registry)
        assert spec.nodes, f"{preset.name} has no nodes"
        assert preset.description
