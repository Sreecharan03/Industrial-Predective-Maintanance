"""Parity + performance: the Operational Timeline engine must reproduce the
Phase-2 Runtime Behaviour numbers for SC-126.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest
from senseminds.engines.operating_state import OperatingStateEngine
from senseminds.engines.operational_timeline import OperationalTimelineEngine
from senseminds.engines.operational_timeline import runtime_math as rt
from senseminds.ingestion import ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_PHASE2_DAILY = _ROOT / "reports" / "data" / "SC-126_Compressor_daily_runtime.csv"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _PHASE2_DAILY.exists(),
    reason="Phase-2 data not available on this machine",
)


@pytest.fixture(scope="module")
def machine():  # noqa: ANN201
    series = ProcessedCsvSource(_PROCESSED).load("SC-126")
    states = OperatingStateEngine().compute(series)
    return OperationalTimelineEngine().compute(states).machine("Compressor"), states


def test_runtime_rollup_matches_phase2(machine) -> None:  # noqa: ANN001
    tl, _ = machine
    r = tl.runtime
    # Phase-2 Runtime report: 927 days, ~100% util, 80 running / 11 idle blocks.
    assert r.days_with_data == 927
    assert r.avg_utilization_pct == pytest.approx(99.97, abs=0.05)
    assert r.n_running_segments == 80
    assert r.n_idle_segments == 11
    # daily running-hours distribution: P5=21.5, median=24.0, P95=24.4
    assert r.daily_running_hours_p5 == pytest.approx(21.5, abs=0.1)
    assert r.daily_running_hours_median == pytest.approx(24.0, abs=0.1)
    assert r.daily_running_hours_p95 == pytest.approx(24.4, abs=0.1)


def test_longest_run_matches_phase2(machine) -> None:  # noqa: ANN001
    tl, _ = machine
    longest = tl.runtime.longest_run
    # Phase-2: longest continuous run 76.7 days (2024-12-03 to 2025-02-17).
    assert longest.duration_hours / 24.0 == pytest.approx(76.7, abs=0.1)
    assert longest.start.date().isoformat() == "2024-12-03"
    assert longest.end.date().isoformat() == "2025-02-17"
    assert tl.runtime.median_run_hours / 24.0 == pytest.approx(2.41, abs=0.05)


def test_daily_table_matches_phase2_csv(machine) -> None:  # noqa: ANN001
    _, states = machine
    m = states.machine("Compressor")
    frame = rt.episodes_to_frame(
        [
            {"start": e.start, "end": e.end, "dur_min": e.dur_min, "final_state": e.final_state}
            for e in m.episodes
        ]
    )
    got = rt.daily_runtime_table(frame).reset_index(drop=True)
    exp = pd.read_csv(_PHASE2_DAILY)
    got["date"] = got["date"].astype(str)
    merged = got.merge(exp, on="date", suffixes=("_got", "_exp"))
    assert len(merged) == len(exp)  # every Phase-2 day reproduced
    assert (merged["covered_hours_got"] - merged["covered_hours_exp"]).abs().max() < 1e-6
    assert (merged["utilization_pct_got"] - merged["utilization_pct_exp"]).abs().max() < 1e-6


def test_performance_full_unit_under_budget(machine) -> None:  # noqa: ANN001
    _, states = machine
    start = time.perf_counter()
    tl = OperationalTimelineEngine().compute(states).machine("Compressor")
    elapsed = time.perf_counter() - start
    # ~3000 episodes -> timeline should build well under a generous budget
    assert elapsed < 5.0
    assert len(tl.events) == sum(len(m.episodes) for m in states.machines)
