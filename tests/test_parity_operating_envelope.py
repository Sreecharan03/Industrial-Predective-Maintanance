"""Parity: the Operating Envelope engine must reproduce Phase-2's SC-126
operating-envelope report exactly (within float tolerance).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.catalog import sensor_key
from senseminds.engines.operating_envelope import OperatingEnvelopeEngine
from senseminds.engines.statistics import StatisticsEngine
from senseminds.ingestion import ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_PHASE2_ENV = _ROOT / "reports" / "data" / "SC-126_operating_envelope.csv"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _PHASE2_ENV.exists(),
    reason="Phase-1/2 data not available on this machine",
)


@pytest.fixture(scope="module")
def result():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    stats = StatisticsEngine().compute(series)
    return OperatingEnvelopeEngine().compute(series, stats)


@pytest.fixture(scope="module")
def phase2():  # noqa: ANN201
    return pd.read_csv(_PHASE2_ENV).set_index("sensor")


def _match(got: float | None, expected) -> bool:  # noqa: ANN001
    if pd.isna(expected):
        return got is None
    return got is not None and got == pytest.approx(float(expected), rel=1e-6)


@pytest.mark.parametrize(
    "source_col",
    [
        "Suction Pressure", "Discharge Pressure", "Oil Pressure", "Oil Temp",
        "Discharge Temp", "Running Amperes", "Loading Percentage",
    ],
)
def test_envelope_matches_phase2(result, phase2, source_col) -> None:  # noqa: ANN001
    exp = phase2.loc[source_col]
    env = result.sensor(sensor_key(source_col))
    b = env.bands

    # percentile bands (sourced from Statistics engine)
    assert _match(b.normal_window.low, exp["normal_window_p5"])
    assert _match(b.normal_window.high, exp["normal_window_p95"])
    assert _match(b.typical_range.low, exp["typical_range_p25"])
    assert _match(b.typical_range.high, exp["typical_range_p75"])
    assert _match(b.cv_pct, exp["cv_pct"])

    # mode band (histogram) - may be absent
    if pd.isna(exp["mode_band_share_pct"]):
        assert b.mode_band is None
    else:
        assert _match(b.mode_band.low, exp["mode_band_low"])
        assert _match(b.mode_band.high, exp["mode_band_high"])
        assert _match(b.mode_band.share_pct, exp["mode_band_share_pct"])

    # rare region - may be absent
    if pd.isna(exp["rare_pct_of_readings"]):
        assert b.rare_region is None
    else:
        assert _match(b.rare_region.pct_of_readings, exp["rare_pct_of_readings"])
        assert _match(b.rare_region.low_end, exp["rare_low_end"])
        assert _match(b.rare_region.high_start, exp["rare_high_start"])
