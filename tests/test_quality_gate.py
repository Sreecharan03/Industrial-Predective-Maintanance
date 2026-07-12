"""Quality gate: injected defects are counted correctly."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from senseminds.engines.quality import QualityGate
from senseminds.ingestion import ProcessedCsvSource


def _synthetic_sc126(tmp_path: Path) -> Path:
    n = 200
    ts = list(pd.date_range("2024-01-01", periods=n, freq="30min"))
    ts = ts[:100] + [t + pd.Timedelta(days=2) for t in ts[100:]]  # one big gap
    ts[50] = ts[49]  # one duplicate timestamp

    sp = np.linspace(16.0, 18.0, n)
    sp[0] = -0.5  # one negative pressure
    sp[60:66] = 17.0  # a flatline run of 6

    lp = np.full(n, 95.0)
    lp[:10] = 101.0  # 10 out-of-range loading %

    ot = np.random.default_rng(0).uniform(50.0, 56.0, n)
    ot[:40] = -49.5  # fault-code pattern (40 repeats, far below median)

    path = tmp_path / "SC-126.csv"
    pd.DataFrame(
        {
            "timestamp": [t.isoformat() for t in ts],
            "Suction Pressure": sp,
            "Loading Percentage": lp,
            "Oil Temp": ot,
        }
    ).to_csv(path, index=False)
    return path


def test_quality_gate_counts_injected_defects(tmp_path: Path) -> None:
    _synthetic_sc126(tmp_path)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    result = QualityGate(gap_threshold_hours=4.0).evaluate(series)

    assert result.n_rows == 200
    assert result.sensor("suction_pressure").n_negative == 1
    assert result.sensor("suction_pressure").longest_flatline_run >= 6
    assert result.sensor("loading_percentage").n_out_of_range == 10
    ot = result.sensor("oil_temp")
    assert ot.fault_code_value == -49.5
    assert ot.fault_code_count == 40
    assert result.n_duplicate_timestamps == 1
    assert result.n_gaps >= 1
    assert result.largest_gap_hours is not None and result.largest_gap_hours > 24


def test_quality_result_is_persistable(tmp_path: Path) -> None:
    from senseminds.engines.quality import QualityResult
    from senseminds.infrastructure.artifact_store import LocalArtifactStore

    _synthetic_sc126(tmp_path)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    result = QualityGate().evaluate(series)

    store = LocalArtifactStore(tmp_path / "artifacts")
    store.save(result)
    loaded = store.load(result.artifact_id, QualityResult)
    assert loaded == result
    assert loaded.provenance.engine == "quality"
