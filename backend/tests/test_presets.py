"""Presets: versioned, file-backed, shareable (ARCHITECTURE.md section 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from restoration.core.errors import PipelineValidationError
from restoration.presets import Preset, PresetStore, load_preset_file, validate_name

PIPELINE = {
    "version": 1,
    "nodes": [{"id": "a", "type": "realesrgan", "params": {"scale": 4}}],
    "edges": [],
}


def test_round_trip(tmp_path: Path):
    store = PresetStore(tmp_path)
    store.save(Preset(name="My Preset", pipeline=PIPELINE, description="4x"))

    loaded = store.get("My Preset")
    assert loaded.pipeline == PIPELINE
    assert loaded.description == "4x"
    assert loaded.version == 1


def test_list_and_delete(tmp_path: Path):
    store = PresetStore(tmp_path)
    assert store.list() == []

    store.save(Preset(name="b", pipeline=PIPELINE))
    store.save(Preset(name="a", pipeline=PIPELINE))
    assert [p.name for p in store.list()] == ["a", "b"]  # sorted by filename

    assert store.delete("a") is True
    assert store.delete("a") is False
    assert [p.name for p in store.list()] == ["b"]


def test_missing_preset_raises(tmp_path: Path):
    with pytest.raises(PipelineValidationError, match="no preset named"):
        PresetStore(tmp_path).get("ghost")


def test_a_corrupt_preset_does_not_break_the_listing(tmp_path: Path):
    store = PresetStore(tmp_path)
    store.save(Preset(name="good", pipeline=PIPELINE))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    assert [p.name for p in store.list()] == ["good"]


@pytest.mark.parametrize("name", ["../escape", "a/b", "", "x" * 65, ".hidden", "a\\b"])
def test_unsafe_names_are_rejected(name: str, tmp_path: Path):
    with pytest.raises(PipelineValidationError, match="invalid preset name"):
        validate_name(name)
    with pytest.raises(PipelineValidationError):
        PresetStore(tmp_path).get(name)


@pytest.mark.parametrize("name", ["ok", "with space", "dash-ok", "under_score", "v1.2"])
def test_safe_names_are_accepted(name: str):
    assert validate_name(name) == name


def test_unsupported_version_rejected():
    with pytest.raises(PipelineValidationError, match="version"):
        Preset.from_dict({"version": 2, "name": "x", "pipeline": PIPELINE})


def test_missing_fields_rejected():
    with pytest.raises(PipelineValidationError, match="needs a 'name'"):
        Preset.from_dict({"version": 1, "name": "x"})


def test_load_preset_file_accepts_a_full_envelope(tmp_path: Path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"version": 1, "name": "n", "pipeline": PIPELINE}), "utf-8")
    assert load_preset_file(path).name == "n"


def test_load_preset_file_accepts_a_bare_pipeline_document(tmp_path: Path):
    """The executor's own JSON is what people will have lying around."""
    path = tmp_path / "chain.json"
    path.write_text(json.dumps(PIPELINE), "utf-8")

    preset = load_preset_file(path)
    assert preset.name == "chain"
    assert preset.pipeline == PIPELINE


def test_load_preset_file_reports_bad_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{", "utf-8")
    with pytest.raises(PipelineValidationError, match="invalid JSON"):
        load_preset_file(path)


def test_load_preset_file_reports_a_missing_file(tmp_path: Path):
    with pytest.raises(PipelineValidationError, match="cannot read preset"):
        load_preset_file(tmp_path / "nope.json")


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path: Path):
    store = PresetStore(tmp_path)
    store.save(Preset(name="x", pipeline=PIPELINE))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.json"]
