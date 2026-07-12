"""Parity: the Reliability engine must reproduce Phase-2 step11's SC-126
reliability scores and signals exactly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.catalog import sensor_key
from senseminds.engines.quality import QualityGate
from senseminds.engines.reliability import ReliabilityEngine
from senseminds.engines.statistics import StatisticsEngine
from senseminds.ingestion import ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_PHASE2 = _ROOT / "reports" / "data" / "sensor_reliability_ranking.csv"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _PHASE2.exists(),
    reason="Phase-2 data not available on this machine",
)


@pytest.fixture(scope="module")
def result():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    quality = QualityGate().evaluate(series)
    stats = StatisticsEngine().compute(series)
    return ReliabilityEngine().compute(series, quality, stats)


@pytest.fixture(scope="module")
def phase2():  # noqa: ANN201
    df = pd.read_csv(_PHASE2)
    return df[df["unit"] == "SC-126"].set_index("sensor")


@pytest.mark.parametrize(
    "source_col",
    [
        "Suction Pressure", "Discharge Pressure", "Oil Pressure", "Oil Temp",
        "Running Amperes", "Loading Percentage", "Condenser Entering Temp",
    ],
)
def test_reliability_matches_phase2(result, phase2, source_col) -> None:  # noqa: ANN001
    r = result.sensor(sensor_key(source_col))
    exp = phase2.loc[source_col]
    assert r.reliability_score == pytest.approx(float(exp["reliability_score"]), abs=0.1)
    assert r.signals.missing_pct == pytest.approx(float(exp["missing_pct"]), abs=0.01)
    assert r.signals.pct_in_flatline_runs == pytest.approx(
        float(exp["pct_in_flatline_runs_ge5"]), abs=0.01
    )
    assert r.signals.fault_code_pct == pytest.approx(float(exp["fault_code_pct"]), abs=0.01)
    assert r.signals.noise_level == pytest.approx(float(exp["noise_level"]), abs=0.001)
