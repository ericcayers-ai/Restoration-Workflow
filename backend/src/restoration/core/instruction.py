"""InstructionRestorer protocol + InstructIR prompt library loader.

InstructIR is the shipped Master Restorer. A Defusion (or successor) backend can
implement the same protocol / occupy the ``instructir`` node-id alias later
without redesigning the prompt library, ensemble conductor, or Studio UI.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .types import ImageArray, RunContext


@runtime_checkable
class InstructionRestorer(Protocol):
    """Swappable instruction-guided restoration backend."""

    id: str

    def restore_with_instruction(
        self,
        image: ImageArray,
        instruction: str,
        params: dict[str, Any],
        ctx: RunContext,
    ) -> ImageArray: ...


def load_instructir_prompts(path: str | Path | None = None) -> dict[str, Any]:
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    text = (
        resources.files("restoration.core") / "data" / "instructir_prompts.json"
    ).read_text(encoding="utf-8")
    return json.loads(text)


def list_prompt_presets(path: str | Path | None = None) -> list[dict[str, Any]]:
    data = load_instructir_prompts(path)
    return list(data.get("presets", []))


def prompt_by_id(preset_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    for preset in list_prompt_presets(path):
        if preset.get("id") == preset_id:
            return preset
    return None


def prompt_for_workflow(
    workflow_name: str, path: str | Path | None = None
) -> dict[str, Any] | None:
    for preset in list_prompt_presets(path):
        pairs = preset.get("pairs_with_workflow") or []
        if workflow_name in pairs:
            return preset
    return None
