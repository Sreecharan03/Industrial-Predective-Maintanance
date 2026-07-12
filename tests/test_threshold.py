"""Threshold engine - behaviour (edge cases) and contract tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from senseminds.domain.enums import Severity, ThresholdStatus
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.operating_envelope import OperatingEnvelopeEngine
from senseminds.engines.statistics import StatisticsEngine
from senseminds.engines.threshold import (
    ThresholdBand,
    ThresholdEngine,
    ThresholdResult,
    ThresholdState,
)
from senseminds.ingestion import ProcessedCsvSource


def _pipeline(tmp_path: Path, values: dict[str, list], unit: str = "SC-126"):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    filename = {"SC-126": "SC-126.csv", "COM-102": "COM-102.csv"}[unit]
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / filename, index=False
    )
    series = ProcessedCsvSource(tmp_path).load(unit)
    envelope = OperatingEnvelopeEngine().compute(series, StatisticsEngine().compute(series))
    return series, envelope


# ----------------------------- behaviour -----------------------------

def test_missing_threshold_is_unknown_not_breach(tmp_path: Path) -> None:
    # Suction Temp exists in SC-126 data but has NO supplied threshold.
    series, env = _pipeline(tmp_path, {"Suction Temp": list(np.linspace(-20, -5, 100))})
    r = ThresholdEngine().compute(series, env).sensor("suction_temp")
    assert r.status is ThresholdStatus.REQUIRES_MANUAL_VALIDATION
    assert r.current_state is ThresholdState.UNKNOWN
    assert r.history is None
    assert r.active_violations == ()


def test_utility_unit_has_all_missing_thresholds(tmp_path: Path) -> None:
    series, env = _pipeline(
        tmp_path, {"Oil Pressure (kg/cm2)": [1.4] * 100}, unit="COM-102"
    )
    r = ThresholdEngine().compute(series, env).sensor("oil_pressure")
    assert r.status is ThresholdStatus.MISSING
    assert r.current_state is ThresholdState.UNKNOWN


def test_within_range_latest_reading(tmp_path: Path) -> None:
    series, env = _pipeline(tmp_path, {"Suction Pressure": [20.0] * 100})  # threshold 10-30
    r = ThresholdEngine().compute(series, env).sensor("suction_pressure")
    assert r.current_state is ThresholdState.WITHIN_RANGE
    assert r.severity is Severity.OK
    assert r.history.n_outside_operating == 0


def test_outside_operating_latest_reading(tmp_path: Path) -> None:
    vals = [20.0] * 99 + [35.0]  # last reading above operating max (30)
    series, env = _pipeline(tmp_path, {"Suction Pressure": vals})
    r = ThresholdEngine().compute(series, env).sensor("suction_pressure")
    assert r.current_state is ThresholdState.OUTSIDE_OPERATING
    assert r.severity is Severity.WARNING
    assert "above operating max" in r.active_violations


def test_protection_setpoint_trip(tmp_path: Path) -> None:
    # SC-126 discharge pressure: operating 235-247, trip 297.
    vals = [240.0] * 99 + [300.0]
    series, env = _pipeline(tmp_path, {"Discharge Pressure": vals})
    r = ThresholdEngine().compute(series, env).sensor("discharge_pressure")
    assert r.current_state is ThresholdState.TRIP
    assert r.severity is Severity.CRITICAL
    assert "trip" in r.active_violations
    names = [pc.name for pc in r.history.protection_counts]
    assert names == ["critical", "unload", "trip"]


def test_invalid_threshold_ordering_rejected() -> None:
    with pytest.raises(ValidationError, match="exceeds high"):
        ThresholdBand(low=30, high=10)


def test_unit_mismatch_raises(tmp_path: Path) -> None:
    series, env = _pipeline(tmp_path, {"Suction Pressure": [20.0] * 100})
    wrong = env.model_copy(update={"unit": "COM-102"})
    with pytest.raises(EngineInputError, match="does not match"):
        ThresholdEngine().compute(series, wrong)


def test_negative_values_counted_as_outside(tmp_path: Path) -> None:
    vals = [-5.0] * 50 + [20.0] * 50  # negatives are below operating min (10)
    series, env = _pipeline(tmp_path, {"Suction Pressure": vals})
    r = ThresholdEngine().compute(series, env).sensor("suction_pressure")
    assert r.history.n_outside_operating == 50


# ----------------------------- contract -----------------------------

def test_result_is_immutable(tmp_path: Path) -> None:
    series, env = _pipeline(tmp_path, {"Suction Pressure": [20.0] * 100})
    result = ThresholdEngine().compute(series, env)
    with pytest.raises(ValidationError):
        result.unit = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        result.sensors[0].current_state = ThresholdState.TRIP  # type: ignore[misc]


def test_serialization_round_trip(tmp_path: Path) -> None:
    series, env = _pipeline(tmp_path, {"Discharge Pressure": list(np.linspace(200, 260, 100))})
    result = ThresholdEngine().compute(series, env)
    restored = ThresholdResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_provenance_and_ownership(tmp_path: Path) -> None:
    series, env = _pipeline(tmp_path, {"Suction Pressure": [20.0] * 100})
    result = ThresholdEngine().compute(series, env)
    assert result.provenance.engine == "threshold"
    assert result.provenance.engine_version == "0.1.0"
