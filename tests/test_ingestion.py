"""Ingestion: CSV source validation and typed output."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from senseminds.ingestion import IngestionError, ProcessedCsvSource
from senseminds.ingestion.models import TIMESTAMP_COLUMN


def _write_csv(path: Path, rows: dict[str, list]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_load_maps_columns_to_sensor_keys(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "SC-126.csv",
        {
            "Date": ["Sat Sep 30 2023", "Sat Sep 30 2023"],
            "Time": ["00:00", "00:30"],
            "Suction Pressure": [17.5, 18.0],
            "Loading Percentage": [100.0, 99.5],
            "Remarks": ["NA", "NA"],
            "source_file": ["f", "f"],
            "timestamp": ["2023-09-30 00:00:00", "2023-09-30 00:30:00"],
        },
    )
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    assert list(series.manifest.sensor_keys) == ["suction_pressure", "loading_percentage"]
    assert TIMESTAMP_COLUMN in series.frame.columns
    assert series.manifest.n_rows == 2
    assert series.manifest.n_sensors == 2
    assert set(series.sensor_frame().columns) == {"suction_pressure", "loading_percentage"}


def test_available_units_reflects_present_files(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "SC-126.csv",
        {"timestamp": ["2023-09-30 00:00:00"], "Suction Pressure": [1.0]},
    )
    assert ProcessedCsvSource(tmp_path).available_units() == ["SC-126"]


def test_missing_timestamp_column_raises(tmp_path: Path) -> None:
    _write_csv(tmp_path / "SC-126.csv", {"Suction Pressure": [1.0]})
    with pytest.raises(IngestionError, match="timestamp"):
        ProcessedCsvSource(tmp_path).load("SC-126")


def test_unparseable_timestamp_raises(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "SC-126.csv",
        {"timestamp": ["not-a-date"], "Suction Pressure": [1.0]},
    )
    with pytest.raises(IngestionError, match="unparseable"):
        ProcessedCsvSource(tmp_path).load("SC-126")


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="not found"):
        ProcessedCsvSource(tmp_path).load("SC-126")
