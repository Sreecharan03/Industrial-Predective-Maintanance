"""Parity: the refactored ingestion + quality gate must reproduce the exact
Phase-1 Data Quality / Inspection numbers for the real SC-126 data.

This is the regression guard that proves the platform refactor is
behaviour-preserving, not a rewrite that quietly changed the analysis. Skipped
if the Phase-1 processed CSVs are not present on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from senseminds.engines.quality import QualityGate
from senseminds.ingestion import ProcessedCsvSource

_PROCESSED = Path(__file__).resolve().parents[2] / "Datasets" / "processed"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists(),
    reason="Phase-1 processed CSVs not available on this machine",
)


@pytest.fixture(scope="module")
def sc126_quality():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    return QualityGate().evaluate(series)


def test_row_count_matches_phase1(sc126_quality) -> None:  # noqa: ANN001
    # Dataset Inspection Report: SC-126 rows = 42,955.
    assert sc126_quality.n_rows == 42955


def test_missing_counts_match_phase1(sc126_quality) -> None:  # noqa: ANN001
    # Inspection Report: 497 missing for most sensors, 499 for condenser temps.
    assert sc126_quality.sensor("suction_pressure").n_missing == 497
    assert sc126_quality.sensor("discharge_pressure").n_missing == 497
    assert sc126_quality.sensor("condenser_entering_temp").n_missing == 499
    assert sc126_quality.sensor("condenser_leaving_temp").n_missing == 499


def test_physical_validity_matches_phase1(sc126_quality) -> None:  # noqa: ANN001
    # Data Quality Report: 1 negative Suction Pressure (min -0.61);
    # 25,907 Loading Percentage readings outside 0-100.
    assert sc126_quality.sensor("suction_pressure").n_negative == 1
    assert sc126_quality.sensor("loading_percentage").n_out_of_range == 25907


def test_fault_code_matches_phase1(sc126_quality) -> None:  # noqa: ANN001
    # Data Quality Report: Oil Temp fault code -49.5 across 401 readings.
    ot = sc126_quality.sensor("oil_temp")
    assert ot.fault_code_value == -49.5
    assert ot.fault_code_count == 401
