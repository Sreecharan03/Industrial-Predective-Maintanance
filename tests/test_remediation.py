"""Architecture remediation (ADR-011): pipeline/context, threshold-envelope
context, catalog subsystems, and cross-engine immutability."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.application import (
    AnalysisContext,
    DeterministicPipeline,
    MissingDependencyError,
)
from senseminds.catalog import build_asset
from senseminds.engines.statistics import StatisticsResult
from senseminds.ingestion import ProcessedCsvSource


def _series(tmp_path: Path, values: dict[str, list]):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    return ProcessedCsvSource(tmp_path).load("SC-126")


# --- R5: pipeline + AnalysisContext ---

def test_pipeline_populates_full_context(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Loading Percentage": [0.0] * 100 + [100.0] * 100})
    ctx = DeterministicPipeline().run(series)
    assert ctx.unit == "SC-126"
    for name in ("statistics", "operating_state", "envelope", "threshold", "timeline"):
        assert getattr(ctx, name) is not None
    ctx.require("statistics", "threshold", "timeline")  # should not raise


def test_context_require_raises_on_missing(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Loading Percentage": [100.0] * 50})
    ctx = AnalysisContext(unit="SC-126", series=series)
    with pytest.raises(MissingDependencyError, match="threshold"):
        ctx.require("threshold")


# --- R4: catalog subsystems ---

def test_catalog_populates_subsystems() -> None:
    asset = build_asset(
        "SC-126",
        ["timestamp", "Oil Pressure", "Oil Temp", "Suction Pressure", "Condenser Entering Temp"],
    )
    subs = {s.key: set(s.sensor_keys) for s in asset.subsystems}
    assert subs["oil_system"] == {"oil_pressure", "oil_temp"}
    assert "suction_pressure" in subs["compression"]
    assert "condenser_entering_temp" in subs["condenser"]


# --- R3: threshold uses envelope for historical context ---

def test_threshold_carries_envelope_historical_context(tmp_path: Path) -> None:
    # Discharge Pressure operating 235-247, but here the machine runs ~200
    # (typical operation BELOW the threshold) -> context must say so.
    series = _series(tmp_path, {"Discharge Pressure": [200.0] * 100 + [205.0] * 100})
    ctx = DeterministicPipeline().run(series)
    r = ctx.threshold.sensor("discharge_pressure")
    assert r.evidence.historical_context  # non-empty
    assert "BELOW" in r.evidence.historical_context


# --- R1: cross-engine immutability (statistics/state now frozen too) ---

def test_statistics_result_is_frozen(tmp_path: Path) -> None:
    from pydantic import ValidationError

    series = _series(tmp_path, {"Suction Pressure": [17.0] * 100})
    stats: StatisticsResult = DeterministicPipeline().run(series).statistics
    with pytest.raises(ValidationError):
        stats.unit = "x"  # type: ignore[misc]
