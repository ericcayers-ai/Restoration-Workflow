"""Node registry & plugin discovery (ARCHITECTURE.md sections 3 and 7).

In-box nodes register via ``register()``. Third-party plugins are discovered
from a ``plugins/`` directory at startup: each ``plugins/<name>/`` contains a
``manifest.json`` plus a Python module — no core-code edits required. A broken
plugin is recorded and skipped, never fatal.

manifest.json contract (the whole contract — Phase 6 documents it standalone):

    {
      "name": "my-plugin",
      "version": "1.0.0",
      "module": "plugin.py",          // relative to the plugin dir
      "nodes": ["MyNodeClass", ...]   // BaseRestorationNode subclasses in it
    }
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import PipelineValidationError, PluginError
from .types import BaseRestorationNode, NodeCategory


class NodeRegistry:
    """Single source of truth for which node types exist."""

    def __init__(self) -> None:
        self._factories: dict[str, type[BaseRestorationNode]] = {}
        self._plugin_errors: list[dict[str, str]] = []

    # -- registration -----------------------------------------------------------

    def register(self, node_cls: type[BaseRestorationNode]) -> None:
        node_id = node_cls.id
        if not node_id:
            raise PluginError(f"{node_cls.__name__} has an empty id")
        if node_id in self._factories and self._factories[node_id] is not node_cls:
            raise PluginError(f"duplicate node id '{node_id}'")
        self._factories[node_id] = node_cls

    def register_builtins(self) -> None:
        from ..nodes import BUILTIN_NODES  # noqa: PLC0415 (avoid import cycle)
        for cls in BUILTIN_NODES:
            self.register(cls)

    # -- plugin discovery ---------------------------------------------------------

    def discover_plugins(self, plugins_dir: Path | str) -> None:
        plugins_dir = Path(plugins_dir)
        if not plugins_dir.is_dir():
            return
        for entry in sorted(plugins_dir.iterdir()):
            manifest = entry / "manifest.json"
            if entry.is_dir() and manifest.exists():
                try:
                    self._load_plugin(entry, manifest)
                except Exception as exc:  # a broken plugin must not kill the app
                    self._plugin_errors.append({"plugin": entry.name, "error": str(exc)})

    def _load_plugin(self, plugin_dir: Path, manifest_path: Path) -> None:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginError(f"invalid manifest.json: {exc}") from exc

        for key in ("name", "module", "nodes"):
            if key not in manifest:
                raise PluginError(f"manifest.json missing required key '{key}'")

        module_path = plugin_dir / manifest["module"]
        if not module_path.exists():
            raise PluginError(f"module file '{manifest['module']}' not found")

        mod_name = f"restoration_plugin_{manifest['name'].replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, module_path)
        if spec is None or spec.loader is None:
            raise PluginError(f"cannot import '{module_path}'")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)

        for class_name in manifest["nodes"]:
            node_cls = getattr(module, class_name, None)
            if node_cls is None:
                raise PluginError(f"class '{class_name}' not found in {manifest['module']}")
            if not issubclass(node_cls, BaseRestorationNode):
                raise PluginError(f"'{class_name}' is not a BaseRestorationNode subclass")
            self.register(node_cls)

    @property
    def plugin_errors(self) -> list[dict[str, str]]:
        return list(self._plugin_errors)

    # -- lookup -------------------------------------------------------------------

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._factories

    def ids(self) -> list[str]:
        return sorted(self._factories)

    def get_class(self, node_id: str) -> type[BaseRestorationNode]:
        try:
            return self._factories[node_id]
        except KeyError:
            raise PipelineValidationError(f"unknown node type '{node_id}'") from None

    def create(self, node_id: str) -> BaseRestorationNode:
        return self.get_class(node_id)()

    def all_nodes(self) -> Iterable[BaseRestorationNode]:
        for node_id in self.ids():
            yield self.create(node_id)

    def describe_all(self) -> list[dict[str, Any]]:
        return [n.describe() for n in self.all_nodes()]

    def fallback_for(self, node: BaseRestorationNode) -> str | None:
        """A concrete lower-tier alternative in the same category, for OOM
        error messages (ARCHITECTURE.md section 4)."""
        candidates = [
            n for n in self.all_nodes()
            if n.category is node.category
            and n.id != node.id
            and n.vram_tier.rank < node.vram_tier.rank
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda n: n.vram_tier.rank).id


def category_of(value: str) -> NodeCategory:
    try:
        return NodeCategory(value)
    except ValueError:
        raise PipelineValidationError(f"unknown node category '{value}'") from None
