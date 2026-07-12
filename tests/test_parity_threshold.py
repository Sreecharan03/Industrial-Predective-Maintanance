"""Parity: the Threshold engine's operating-range breach counts must reproduce
Phase-1 exactly (threshold_violations / pct_within / pct_outside for SC-126).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.catalog import sensor_key
from senseminds.engines.operating_envelope import OperatingEnvelopeEngine
from senseminds.engines.statistics import StatisticsEngine
from senseminds.engines.threshold import ThresholdEngine
from senseminds.ingestion import ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_PHASE1_STATS = _ROOT / "reports" / "data" / "SC-126_full_stats.csv"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _PHASE1_STATS.exists(),
    reason="Phase-1 data not available on this machine",
)

_THRESHOLDED = [
    "Suction Pressure", "Discharge Pressure", "Oil Pressure", "Oil Temp",
    "Discharge Temp", "Running Amperes", "Loading Percentage",
]


@pytest.fixture(scope="module")
def result():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    envelope = OperatingEnvelopeEngine().compute(series, StatisticsEngine().compute(series))
    return ThresholdEngine().compute(series, envelope)


@pytest.fixture(scope="module")
def phase1():  # noqa: ANN201
    return pd.read_csv(_PHASE1_STATS).set_index("column")


@pytest.mark.parametrize("source_col", _THRESHOLDED)
def test_breach_counts_match_phase1(result, phase1, source_col) -> None:  # noqa: ANN001
    r = result.sensor(sensor_key(source_col))
    exp = phase1.loc[source_col]
    assert r.history is not None
    assert r.history.n_outside_operating == int(exp["threshold_violations"])
    assert r.history.pct_within == pytest.approx(float(exp["pct_within_threshold"]), abs=0.01)
    assert r.history.pct_outside == pytest.approx(float(exp["pct_outside_threshold"]), abs=0.01)


def test_sc126_discharge_pressure_protection_all_zero(result) -> None:  # noqa: ANN001
    # Phase-1 threshold validation: no reading reached 280/285/297.
    r = result.sensor("discharge_pressure")
    counts = {pc.name: pc.count for pc in r.history.protection_counts}
    assert counts == {"critical": 0, "unload": 0, "trip": 0}


def test_missing_thresholds_flagged(result) -> None:  # noqa: ANN001
    # Suction Temp / condenser temps have no supplied threshold.
    from senseminds.domain.enums import ThresholdStatus

    for key in ("suction_temp", "condenser_entering_temp", "condenser_leaving_temp"):
        r = result.sensor(key)
        assert r.status is ThresholdStatus.REQUIRES_MANUAL_VALIDATION
        assert r.history is None
