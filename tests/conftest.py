"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from senseminds.domain.results import EngineResult
from senseminds.domain.value_objects import Provenance


class SampleResult(EngineResult):
    """A minimal concrete EngineResult used to exercise the artifact store."""

    sensor_key: str
    mean: float


@pytest.fixture
def provenance() -> Provenance:
    return Provenance(
        engine="statistics",
        engine_version="0.1.0",
        source_unit="SC-126",
        input_hash="abc123",
        produced_at=datetime(2026, 7, 10, tzinfo=UTC),
    )


@pytest.fixture
def sample_result(provenance: Provenance) -> SampleResult:
    return SampleResult(
        artifact_id="SC-126__discharge_pressure__stats",
        provenance=provenance,
        sensor_key="discharge_pressure",
        mean=208.77,
    )
