"""Presets: pipeline DAGs saved as versioned JSON (ARCHITECTURE.md section 7).

A preset is a file, not a database row — it is meant to be shared, diffed and
checked into a repo. The on-disk shape is deliberately a thin envelope around
the same pipeline JSON the executor and the REST API already speak, so a preset
can be pasted straight into a job submission and vice versa.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.errors import PipelineValidationError

PRESET_VERSION = 1
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")


@dataclass(frozen=True)
class Preset:
    name: str
    pipeline: dict[str, Any]
    description: str = ""
    version: int = PRESET_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "pipeline": self.pipeline,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Preset:
        if not isinstance(data, dict):
            raise PipelineValidationError("preset must be a JSON object")
        version = data.get("version", PRESET_VERSION)
        if version != PRESET_VERSION:
            raise PipelineValidationError(f"unsupported preset version {version!r}")
        name = data.get("name")
        pipeline = data.get("pipeline")
        if not isinstance(name, str) or not isinstance(pipeline, dict):
            raise PipelineValidationError("preset needs a 'name' and a 'pipeline'")
        return cls(
            name=name,
            pipeline=pipeline,
            description=str(data.get("description", "")),
            version=version,
        )


def validate_name(name: str) -> str:
    """Presets are addressed by name in the API and on disk; keep both safe."""
    if not _SAFE_NAME.match(name or ""):
        raise PipelineValidationError(
            f"invalid preset name {name!r}: use letters, digits, spaces, '.', '_' or '-'"
        )
    return name


class PresetStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / f"{validate_name(name)}.json"

    def list(self) -> list[Preset]:
        if not self.root.is_dir():
            return []
        presets = []
        for path in sorted(self.root.glob("*.json")):
            try:
                presets.append(Preset.from_dict(json.loads(path.read_text("utf-8"))))
            except (json.JSONDecodeError, OSError, PipelineValidationError):
                continue  # a corrupt preset file must not break the listing
        return presets

    def get(self, name: str) -> Preset:
        path = self._path(name)
        if not path.exists():
            raise PipelineValidationError(f"no preset named {name!r}")
        return Preset.from_dict(json.loads(path.read_text("utf-8")))

    def save(self, preset: Preset) -> Path:
        path = self._path(preset.name)
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(preset.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False


def load_preset_file(path: Path | str) -> Preset:
    """Read a preset from an arbitrary path (``restore run --preset ./x.json``)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineValidationError(f"{path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise PipelineValidationError(f"cannot read preset {path}: {exc}") from exc

    # Accept a bare pipeline document as well as a full preset envelope: the
    # executor's own JSON is the thing people will have lying around.
    if "pipeline" not in data and "nodes" in data:
        return Preset(name=path.stem, pipeline=data)
    return Preset.from_dict(data)
