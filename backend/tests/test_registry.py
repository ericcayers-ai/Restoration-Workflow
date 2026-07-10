"""Registry & plugin discovery.

The plugin path is exercised now, in Phase 1, precisely because only in-box nodes
exist yet: if the contract is only proven once a third party depends on it, it
gets retrofitted rather than designed (ROADMAP.md Phase 1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from restoration.core.errors import PipelineValidationError, PluginError
from restoration.core.registry import NodeRegistry, category_of
from restoration.core.types import BaseRestorationNode, NodeCategory, VramTier

from .conftest import RecordingNode

_PLUGIN_MODULE = '''
from restoration.core.types import (
    BaseRestorationNode, LicenseInfo, LicenseKind, NodeCategory, VramTier,
)


class ThirdPartyNode(BaseRestorationNode):
    id = "third_party"
    category = NodeCategory.REGRESSION
    display_name = "Third party"
    license = LicenseInfo(spdx_id="MIT", kind=LicenseKind.PERMISSIVE, source_url="")
    vram_tier = VramTier.LOW

    async def run(self, image, params, ctx):
        return image
'''


def _write_plugin(
    root: Path, name: str, manifest: dict, module: str | None = _PLUGIN_MODULE
) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if module is not None:
        (directory / "plugin.py").write_text(module, encoding="utf-8")
    return directory


def test_register_rejects_empty_and_duplicate_ids():
    registry = NodeRegistry()

    class Nameless(BaseRestorationNode):
        id = ""

    with pytest.raises(PluginError, match="empty id"):
        registry.register(Nameless)

    registry.register(RecordingNode)
    registry.register(RecordingNode)  # same class again is fine

    class Impostor(BaseRestorationNode):
        id = "recording"

    with pytest.raises(PluginError, match="duplicate node id"):
        registry.register(Impostor)


def test_unknown_node_type_is_a_validation_error():
    registry = NodeRegistry()
    with pytest.raises(PipelineValidationError, match="unknown node type"):
        registry.get_class("ghost")


def test_builtins_all_register():
    from restoration.nodes import BUILTIN_NODES

    registry = NodeRegistry()
    registry.register_builtins()
    assert set(registry.ids()) == {cls.id for cls in BUILTIN_NODES}


def test_fallback_for_picks_the_lowest_tier_in_the_same_category(registry):
    node = registry.create("oom_fatal")
    assert registry.fallback_for(node) == "cheap_generative"


def test_fallback_for_returns_none_when_nothing_is_cheaper(registry):
    node = registry.create("cheap_generative")
    assert registry.fallback_for(node) is None


def test_plugin_discovery_registers_a_third_party_node(tmp_path: Path):
    _write_plugin(
        tmp_path,
        "my-plugin",
        {"name": "my-plugin", "version": "1.0.0", "module": "plugin.py",
         "nodes": ["ThirdPartyNode"]},
    )
    registry = NodeRegistry()
    registry.discover_plugins(tmp_path)

    assert "third_party" in registry
    assert registry.plugin_errors == []
    node = registry.create("third_party")
    assert node.category is NodeCategory.REGRESSION
    assert node.vram_tier is VramTier.LOW


def test_missing_plugins_directory_is_not_an_error(tmp_path: Path):
    registry = NodeRegistry()
    registry.discover_plugins(tmp_path / "does-not-exist")
    assert registry.ids() == []


@pytest.mark.parametrize(
    "name, manifest, module",
    [
        ("bad-json", None, _PLUGIN_MODULE),
        ("missing-key", {"name": "missing-key", "module": "plugin.py"}, _PLUGIN_MODULE),
        (
            "missing-module",
            {"name": "missing-module", "module": "nope.py", "nodes": ["ThirdPartyNode"]},
            None,
        ),
        (
            "missing-class",
            {"name": "missing-class", "module": "plugin.py", "nodes": ["Ghost"]},
            _PLUGIN_MODULE,
        ),
        (
            "not-a-node",
            {"name": "not-a-node", "module": "plugin.py", "nodes": ["NotANode"]},
            "class NotANode:\n    pass\n",
        ),
        (
            "explodes-on-import",
            {"name": "explodes-on-import", "module": "plugin.py", "nodes": ["X"]},
            "raise RuntimeError('boom')\n",
        ),
    ],
)
def test_a_broken_plugin_is_recorded_and_skipped(tmp_path: Path, name, manifest, module):
    """A third-party plugin must never take the backend down."""
    directory = tmp_path / name
    directory.mkdir(parents=True)
    if manifest is None:
        (directory / "manifest.json").write_text("{not json", encoding="utf-8")
    else:
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if module is not None:
        (directory / "plugin.py").write_text(module, encoding="utf-8")

    registry = NodeRegistry()
    registry.discover_plugins(tmp_path)  # must not raise

    assert [e["plugin"] for e in registry.plugin_errors] == [name]
    assert registry.ids() == []


def test_one_broken_plugin_does_not_block_a_good_one(tmp_path: Path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.json").write_text("{oops", encoding="utf-8")
    _write_plugin(
        tmp_path,
        "working",
        {"name": "working", "module": "plugin.py", "nodes": ["ThirdPartyNode"]},
    )

    registry = NodeRegistry()
    registry.discover_plugins(tmp_path)
    assert "third_party" in registry
    assert len(registry.plugin_errors) == 1


def test_describe_all_is_serializable(registry):
    described = registry.describe_all()
    assert {d["id"] for d in described} >= {"recording", "merge"}
    json.dumps(described)  # must round-trip to the API layer


def test_category_of():
    assert category_of("face") is NodeCategory.FACE
    with pytest.raises(PipelineValidationError):
        category_of("nonsense")
