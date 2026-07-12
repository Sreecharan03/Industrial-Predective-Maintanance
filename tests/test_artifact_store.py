"""Artifact store: round-trip fidelity, id-safety, and listing."""

from __future__ import annotations

from pathlib import Path

import pytest
from senseminds.infrastructure.artifact_store import (
    ArtifactNotFoundError,
    LocalArtifactStore,
)

from tests.conftest import SampleResult


def test_save_then_load_round_trips(tmp_path: Path, sample_result: SampleResult) -> None:
    store = LocalArtifactStore(tmp_path)
    artifact_id = store.save(sample_result)
    loaded = store.load(artifact_id, SampleResult)
    assert loaded == sample_result
    assert loaded.provenance.source_unit == "SC-126"


def test_load_missing_raises(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ArtifactNotFoundError):
        store.load("nope", SampleResult)


def test_exists_and_list_ids(tmp_path: Path, sample_result: SampleResult) -> None:
    store = LocalArtifactStore(tmp_path)
    assert store.list_ids() == []
    store.save(sample_result)
    assert store.exists(sample_result.artifact_id)
    assert store.list_ids(SampleResult) == [sample_result.artifact_id]
    assert sample_result.artifact_id in store.list_ids()


def test_rejects_path_traversal_ids(tmp_path: Path, provenance) -> None:  # noqa: ANN001
    store = LocalArtifactStore(tmp_path)
    bad = SampleResult(
        artifact_id="../escape", provenance=provenance, sensor_key="x", mean=1.0
    )
    with pytest.raises(ValueError, match="invalid artifact_id"):
        store.save(bad)


def test_overwrite_is_atomic_and_final(tmp_path: Path, sample_result: SampleResult) -> None:
    store = LocalArtifactStore(tmp_path)
    store.save(sample_result)
    updated = sample_result.model_copy(update={"mean": 999.0})
    store.save(updated)
    loaded = store.load(sample_result.artifact_id, SampleResult)
    assert loaded.mean == 999.0
    # exactly one file for that id - no stray temp files left behind
    type_dir = tmp_path / "SampleResult"
    assert sorted(p.suffix for p in type_dir.iterdir()) == [".json"]
