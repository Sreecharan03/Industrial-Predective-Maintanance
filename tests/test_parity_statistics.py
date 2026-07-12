"""Parity: the Statistics engine must reproduce Phase-1's SC-126 full-stats
CSV exactly (within float tolerance). Regression guard on the refactor.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.engines.statistics import StatisticsEngine
from senseminds.ingestion import ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_PHASE1_STATS = _ROOT / "reports" / "data" / "SC-126_full_stats.csv"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _PHASE1_STATS.exists(),
    reason="Phase-1 processed CSV / stats not available on this machine",
)

# Map Phase-1 source column -> catalog sensor key.
_COL_TO_KEY = {
    "Suction Pressure": "suction_pressure",
    "Discharge Pressure": "discharge_pressure",
    "Oil Pressure": "oil_pressure",
    "Oil Temp": "oil_temp",
    "Running Amperes": "running_amperes",
    "Loading Percentage": "loading_percentage",
}


@pytest.fixture(scope="module")
def computed():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    result = StatisticsEngine().compute(series)
    phase1 = pd.read_csv(_PHASE1_STATS).set_index("column")
    return result, phase1


@pytest.mark.parametrize("source_col", list(_COL_TO_KEY))
def test_statistics_match_phase1(computed, source_col) -> None:  # noqa: ANN001
    result, phase1 = computed
    got = result.sensor(_COL_TO_KEY[source_col])
    exp = phase1.loc[source_col]

    assert got.count == int(exp["count"])
    assert got.missing == int(exp["missing"])
    assert got.unique == int(exp["unique"])
    assert got.iqr_outliers == int(exp["iqr_outliers"])
    for got_val, exp_val in [
        (got.minimum, exp["min"]),
        (got.maximum, exp["max"]),
        (got.mean, exp["mean"]),
        (got.median, exp["median"]),
        (got.std, exp["std"]),
        (got.variance, exp["variance"]),
        (got.p5, exp["p5"]),
        (got.p95, exp["p95"]),
        (got.iqr, exp["iqr"]),
        (got.cv_pct, exp["cv_pct"]),
    ]:
        assert got_val == pytest.approx(float(exp_val), rel=1e-6)
