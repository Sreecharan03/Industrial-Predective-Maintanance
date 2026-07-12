"""Domain invariants: the type system must reject unsupported assertions."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError
from senseminds.domain import (
    Confidence,
    EngineeringUnit,
    Provenance,
    Severity,
)


def test_severity_ordering() -> None:
    assert Severity.OK.rank < Severity.WARNING.rank < Severity.CRITICAL.rank


def test_confidence_requires_bounds_and_rationale() -> None:
    ok = Confidence(value=0.8, rationale="three corroborating sensors")
    assert ok.value == 0.8
    with pytest.raises(ValidationError):
        Confidence(value=1.5, rationale="out of range")
    with pytest.raises(ValidationError):
        Confidence(value=0.8, rationale="")  # empty rationale forbidden


def test_provenance_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            engine="statistics",
            engine_version="0.1.0",
            source_unit="SC-126",
            input_hash="h",
            produced_at=datetime(2026, 7, 10),  # naive  # noqa: DTZ001
        )


def test_engineering_unit_tracks_assumed_flag() -> None:
    assumed = EngineeringUnit(symbol="kg/cm2", assumed=True)
    stated = EngineeringUnit(symbol="C")
    assert assumed.assumed is True
    assert stated.assumed is False
    assert assumed != stated
