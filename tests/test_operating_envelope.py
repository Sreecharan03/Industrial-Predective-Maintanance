"""Operating Envelope engine - behaviour (edge cases) and contract tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.operating_envelope import (
    EnvelopeBands,
    EnvelopeEvidence,
    OperatingEnvelopeEngine,
    OperatingEnvelopeResult,
    SensorEnvelope,
)
from senseminds.engines.statistics import StatisticsEngine
from senseminds.engines.statistics.models import StatisticsResult
from senseminds.ingestion import ProcessedCsvSource
from senseminds.ingestion.models import IngestedSeries


def _series_and_stats(
    tmp_path: Path, values: dict[str, list]
) -> tuple[IngestedSeries, StatisticsResult]:
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    frame = {"timestamp": [t.isoformat() for t in ts], **values}
    pd.DataFrame(frame).to_csv(tmp_path / "SC-126.csv", index=False)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    stats = StatisticsEngine().compute(series)
    return series, stats


# ----------------------------- behaviour -----------------------------

def test_constant_values_have_no_mode_or_rare(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": [17.0] * 100})
    env = OperatingEnvelopeEngine().compute(series, stats).sensor("suction_pressure")
    assert env.bands.mode_band is None
    assert env.bands.rare_region is None
    # a percentile window is still defined (all equal -> p5 == p95)
    assert env.bands.normal_window.low == pytest.approx(17.0)


def test_insufficient_history_has_no_mode_band(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": list(np.linspace(10, 20, 10))})
    env = OperatingEnvelopeEngine().compute(series, stats).sensor("suction_pressure")
    assert env.bands.mode_band is None  # < 30 points
    assert env.evidence.sample_count == 10


def test_empty_sensor_stream(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": [np.nan] * 100})
    env = OperatingEnvelopeEngine().compute(series, stats).sensor("suction_pressure")
    assert env.bands.normal_window.low is None and env.bands.normal_window.high is None
    assert env.bands.mode_band is None
    assert env.evidence.sample_count == 0
    assert env.evidence.confidence.value == 0.0


def test_multimodal_distribution_yields_a_mode_band(tmp_path: Path) -> None:
    vals = [10.0] * 60 + [90.0] * 60  # two clear peaks
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": vals})
    env = OperatingEnvelopeEngine().compute(series, stats).sensor("suction_pressure")
    assert env.bands.mode_band is not None
    assert 10.0 <= env.bands.mode_band.low <= 90.0
    # limitation about multimodality is surfaced for the LLM
    assert any("multimodal" in x for x in env.evidence.limitations)


def test_skewed_distribution_is_handled(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    vals = list(rng.exponential(scale=5.0, size=300) + 1.0)
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": vals})
    env = OperatingEnvelopeEngine().compute(series, stats).sensor("suction_pressure")
    assert env.bands.mode_band is not None
    assert env.bands.normal_window.low <= env.bands.median <= env.bands.normal_window.high


def test_low_coverage_lowers_confidence(tmp_path: Path) -> None:
    vals = [17.0] * 50 + [np.nan] * 50  # 50% coverage
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": vals})
    env = OperatingEnvelopeEngine().compute(series, stats).sensor("suction_pressure")
    assert env.evidence.coverage_pct == pytest.approx(50.0)
    assert env.evidence.confidence.value == pytest.approx(0.5)
    assert any("partial history" in x for x in env.evidence.limitations)


def test_unit_mismatch_raises(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": [17.0] * 100})
    wrong = stats.model_copy(update={"unit": "COM-102"})
    with pytest.raises(EngineInputError, match="does not match"):
        OperatingEnvelopeEngine().compute(series, wrong)


def test_missing_sensor_statistics_raises(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": [17.0] * 100})
    empty = stats.model_copy(update={"sensors": ()})
    with pytest.raises(EngineInputError, match="no entry for sensor"):
        OperatingEnvelopeEngine().compute(series, empty)


def test_invalid_engine_parameters_rejected() -> None:
    with pytest.raises(ValueError, match="bins"):
        OperatingEnvelopeEngine(bins=0)
    with pytest.raises(ValueError, match="rare_fraction"):
        OperatingEnvelopeEngine(rare_fraction=1.5)


# ----------------------------- contract -----------------------------

def test_result_is_immutable(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": [17.0] * 100})
    result = OperatingEnvelopeEngine().compute(series, stats)
    with pytest.raises(ValidationError):
        result.unit = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        result.sensors[0].bands.median = 1.0  # type: ignore[misc]


def test_serialization_round_trip(tmp_path: Path) -> None:
    vals = list(np.linspace(10, 20, 100))
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": vals})
    result = OperatingEnvelopeEngine().compute(series, stats)
    restored = OperatingEnvelopeResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_schema_is_stable() -> None:
    assert set(SensorEnvelope.model_fields) == {"sensor_key", "bands", "evidence"}
    assert set(EnvelopeBands.model_fields) == {
        "normal_window", "typical_range", "median", "iqr", "cv_pct", "mode_band", "rare_region",
    }
    assert set(EnvelopeEvidence.model_fields) == {
        "sample_count", "coverage_pct", "missing_pct", "confidence", "assumptions", "limitations",
    }


def test_provenance_carries_engine_version(tmp_path: Path) -> None:
    series, stats = _series_and_stats(tmp_path, {"Suction Pressure": [17.0] * 100})
    result = OperatingEnvelopeEngine().compute(series, stats)
    assert result.provenance.engine == "operating_envelope"
    assert result.provenance.engine_version == "0.1.0"
