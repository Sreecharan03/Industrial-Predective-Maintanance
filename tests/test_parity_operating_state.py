"""Parity: the Operating-State engine must reproduce Phase-2's SC-126 state
summary and cut points exactly. Regression guard on the step6 refactor.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.engines.operating_state import OperatingStateEngine
from senseminds.ingestion import ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_PHASE2_SUMMARY = _ROOT / "reports" / "data" / "SC-126_Compressor_state_summary.csv"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _PHASE2_SUMMARY.exists(),
    reason="Phase-1/2 data not available on this machine",
)


@pytest.fixture(scope="module")
def machine():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    result = OperatingStateEngine().compute(series)
    return result.machine("Compressor")


def test_cutpoints_match_phase2(machine) -> None:  # noqa: ANN001
    # Phase-2 Operating State Report: SC-126 cut points 22.87, 40.82.
    assert len(machine.cutpoints) == 2
    assert machine.cutpoints[0] == pytest.approx(22.87, abs=0.01)
    assert machine.cutpoints[1] == pytest.approx(40.82, abs=0.01)
    assert machine.off_label == "Machine OFF / Idle"


def test_state_summary_matches_phase2(machine) -> None:  # noqa: ANN001
    phase2 = pd.read_csv(_PHASE2_SUMMARY).set_index("final_state")
    assert len(machine.summary) == len(phase2)
    for s in machine.summary:
        exp = phase2.loc[s.state]
        assert s.total_minutes == pytest.approx(float(exp["total_min"]), rel=1e-9)
        assert s.episodes == int(exp["episodes"])
        assert s.avg_episode_minutes == pytest.approx(float(exp["avg_min"]), rel=1e-9)
        assert s.pct_of_covered_time == pytest.approx(float(exp["pct_of_covered_time"]), abs=0.01)


def test_dominant_state_is_full_load(machine) -> None:  # noqa: ANN001
    top = machine.summary[0]  # summary is sorted by total dwell, descending
    assert top.state == "Full Load / Stable Operation"
    assert top.pct_of_covered_time == pytest.approx(91.95, abs=0.01)
