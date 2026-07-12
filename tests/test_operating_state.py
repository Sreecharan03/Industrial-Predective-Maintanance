"""Operating-state engine: segmentation behaviour on controlled input."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from senseminds.engines.operating_state import OperatingStateEngine
from senseminds.ingestion import ProcessedCsvSource


def _bimodal_sc126(tmp_path: Path) -> Path:
    n = 200
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    loading = [0.0] * (n // 2) + [100.0] * (n // 2)  # clear OFF vs full-load split
    path = tmp_path / "SC-126.csv"
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], "Loading Percentage": loading}).to_csv(
        path, index=False
    )
    return path


def test_bimodal_indicator_yields_off_and_full_load(tmp_path: Path) -> None:
    _bimodal_sc126(tmp_path)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    result = OperatingStateEngine().compute(series)

    machine = result.machine("Compressor")
    assert machine is not None
    assert machine.segmentable is True
    assert len(machine.cutpoints) >= 1  # a floor split between OFF (0) and load (100)
    labels = set(machine.band_labels.values())
    assert any("OFF" in x for x in labels)
    assert any("Full Load" in x for x in labels)
    assert machine.off_label == "Machine OFF / Idle"


def test_too_little_data_is_not_segmentable(tmp_path: Path) -> None:
    ts = pd.date_range("2024-01-01", periods=5, freq="30min")
    pd.DataFrame(
        {"timestamp": [t.isoformat() for t in ts], "Loading Percentage": [100.0] * 5}
    ).to_csv(tmp_path / "SC-126.csv", index=False)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    machine = OperatingStateEngine().compute(series).machine("Compressor")
    assert machine.segmentable is False
    assert machine.summary == ()
