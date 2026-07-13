"""Tests for the sixteen built-in workflow presets (ROADMAP.md Phase 4.5.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from restoration.builtin_presets import builtin_preset_names, seed_builtin_presets
from restoration.core.executor import parse_pipeline
from restoration.core.registry import NodeRegistry
from restoration.presets import PresetStore


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register_builtins()
    return reg


def test_sixteen_builtin_preset_definitions():
    names = builtin_preset_names()
    assert len(names) == 16
    assert len(set(names)) == 16


def test_seed_builtin_presets_writes_all_sixteen(tmp_path: Path, registry: NodeRegistry):
    store = PresetStore(tmp_path)
    count = seed_builtin_presets(store, registry)
    assert count == 16
    assert len(store.list()) == 16
    # Idempotent
    assert seed_builtin_presets(store, registry) == 0


def test_each_builtin_preset_is_valid_pipeline(tmp_path: Path, registry: NodeRegistry):
    store = PresetStore(tmp_path)
    seed_builtin_presets(store, registry)
    for preset in store.list():
        spec = parse_pipeline(preset.pipeline, registry)
        assert spec.nodes, f"{preset.name} has no nodes"
        assert preset.description
