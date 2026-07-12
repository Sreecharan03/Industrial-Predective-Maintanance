"""Sensor Trust (Reliability) engine - behaviour and contract tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.quality import QualityGate
from senseminds.engines.reliability import ReliabilityEngine, ReliabilityResult
from senseminds.engines.statistics import StatisticsEngine
from senseminds.ingestion import ProcessedCsvSource


def _inputs(tmp_path: Path, values: dict[str, list]):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    return series, QualityGate().evaluate(series), StatisticsEngine().compute(series)


# ----------------------------- behaviour -----------------------------

def test_clean_sensor_scores_high(tmp_path: Path) -> None:
    # A smooth, well-behaved signal (low mad/std, non-oscillatory) - what a
    # healthy sensor looks like, unlike jittery white noise.
    vals = list(17 + 3 * np.sin(np.linspace(0, 6 * np.pi, 200)))
    series, q, s = _inputs(tmp_path, {"Suction Pressure": vals})
    r = ReliabilityEngine().compute(series, q, s).sensor("suction_pressure")
    assert r.reliability_score > 95
    assert r.sensor_confidence.value > 0.9


def test_flatlined_sensor_scores_lower(tmp_path: Path) -> None:
    vals = [17.0] * 200  # fully flatlined
    series, q, s = _inputs(tmp_path, {"Suction Pressure": vals})
    r = ReliabilityEngine().compute(series, q, s).sensor("suction_pressure")
    assert r.signals.pct_in_flatline_runs > 90
    assert r.reliability_score < 70  # 35% weight fully penalised


def test_spikes_detected(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    vals = list(17 + rng.normal(0, 0.3, 200))
    vals[50] = 60.0  # a clear spike
    vals[150] = -30.0
    series, q, s = _inputs(tmp_path, {"Suction Pressure": vals})
    r = ReliabilityEngine().compute(series, q, s).sensor("suction_pressure")
    assert r.signals.spike_count >= 2


def test_drift_detected(tmp_path: Path) -> None:
    vals = list(np.linspace(10, 30, 200))  # steady ramp -> strong drift
    series, q, s = _inputs(tmp_path, {"Suction Pressure": vals})
    r = ReliabilityEngine().compute(series, q, s).sensor("suction_pressure")
    assert r.signals.drift is not None and r.signals.drift > 1.0


def test_sensors_are_ranked(tmp_path: Path) -> None:
    series, q, s = _inputs(
        tmp_path,
        {
            "Suction Pressure": list(np.random.default_rng(2).normal(17, 0.5, 200)),
            "Oil Temp": [55.0] * 200,  # flatlined -> should rank last
        },
    )
    result = ReliabilityEngine().compute(series, q, s)
    ranks = {sr.sensor_key: sr.rank for sr in result.sensors}
    assert ranks["suction_pressure"] < ranks["oil_temp"]
    assert [sr.rank for sr in result.sensors] == sorted(sr.rank for sr in result.sensors)


def test_unit_mismatch_raises(tmp_path: Path) -> None:
    series, q, s = _inputs(tmp_path, {"Suction Pressure": [17.0] * 100})
    with pytest.raises(EngineInputError, match="unit mismatch"):
        ReliabilityEngine().compute(series, q.model_copy(update={"unit": "COM-102"}), s)


# ----------------------------- contract -----------------------------

def test_result_is_immutable_and_serializable(tmp_path: Path) -> None:
    series, q, s = _inputs(tmp_path, {"Suction Pressure": [17.0] * 100})
    result = ReliabilityEngine().compute(series, q, s)
    with pytest.raises(ValidationError):
        result.unit = "x"  # type: ignore[misc]
    restored = ReliabilityResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert result.provenance.engine == "reliability"
