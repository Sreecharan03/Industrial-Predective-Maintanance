"""Processed-CSV ingestion source.

Reads the Phase-1 cleaned ``processed/<unit>.csv`` files into typed
`IngestedSeries`, mapping each source column to its catalog sensor key and
validating timestamp integrity. This is the ingestion source of truth for the
current build (per the M1 decision); the PDF-extraction path is a future
adapter behind the same `TimeSeriesSource` interface.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from senseminds.catalog import build_asset
from senseminds.catalog.reference_data import NON_SENSOR_COLUMNS, sensor_key
from senseminds.infrastructure.logging import get_logger
from senseminds.ingestion.base import IngestionError, TimeSeriesSource
from senseminds.ingestion.models import TIMESTAMP_COLUMN, IngestedSeries, IngestionManifest

_log = get_logger(__name__)

# Unit -> processed CSV filename (matches Phase-1 UNIT_FILE_MAP).
_UNIT_FILE_MAP: dict[str, str] = {
    "SC-126": "SC-126.csv",
    "SC-114": "SC-114.csv",
    "SC-104": "SC-104.csv",
    "COM-102": "COM-102.csv",
    "COM-110": "COM-110.csv",
    "COM103 & NP102": "COM103_and_NP102.csv",
}


class ProcessedCsvSource(TimeSeriesSource):
    """Ingest the Phase-1 processed CSVs from a directory."""

    def __init__(self, processed_dir: Path) -> None:
        self._dir = Path(processed_dir)

    def available_units(self) -> list[str]:
        return [u for u, f in _UNIT_FILE_MAP.items() if (self._dir / f).exists()]

    def load(self, unit: str) -> IngestedSeries:
        if unit not in _UNIT_FILE_MAP:
            raise IngestionError(f"unknown unit {unit!r}")
        path = self._dir / _UNIT_FILE_MAP[unit]
        if not path.exists():
            raise IngestionError(f"processed CSV not found for {unit!r}: {path}")

        raw = pd.read_csv(path)
        if TIMESTAMP_COLUMN not in raw.columns:
            raise IngestionError(f"{unit!r} CSV missing required '{TIMESTAMP_COLUMN}' column")

        # Parse timestamp; a failure to parse is a hard ingestion error, not a
        # silent NaT that would corrupt every downstream time calculation.
        ts = pd.to_datetime(raw[TIMESTAMP_COLUMN], errors="coerce")
        n_unparseable = int(ts.isna().sum())
        if n_unparseable:
            raise IngestionError(
                f"{unit!r} has {n_unparseable} unparseable timestamp(s)"
            )

        asset = build_asset(unit, list(raw.columns), strict=True)
        rename = {s.source_column: s.key for s in asset.sensors}
        sensor_cols = [c for c in raw.columns if c not in NON_SENSOR_COLUMNS]
        # Guard: every non-catalog-mapped sensor column would have raised in
        # build_asset already; assert the rename covers all sensor columns.
        unmapped = [c for c in sensor_cols if c not in rename]
        if unmapped:
            raise IngestionError(f"{unit!r} has unmapped sensor columns: {unmapped}")

        frame = raw.rename(columns=rename)
        frame[TIMESTAMP_COLUMN] = ts
        frame = frame.sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)

        sensor_keys = tuple(sensor_key(c) for c in sensor_cols)
        keep = [TIMESTAMP_COLUMN, *sensor_keys]
        frame = frame[keep]

        manifest = IngestionManifest(
            unit=unit,
            source=str(path),
            n_rows=len(frame),
            n_sensors=len(sensor_keys),
            start=frame[TIMESTAMP_COLUMN].min().to_pydatetime() if len(frame) else None,
            end=frame[TIMESTAMP_COLUMN].max().to_pydatetime() if len(frame) else None,
            sensor_keys=sensor_keys,
        )
        _log.info(
            "unit_ingested",
            extra={"unit": unit, "n_rows": manifest.n_rows, "n_sensors": manifest.n_sensors},
        )
        return IngestedSeries(asset=asset, frame=frame, manifest=manifest)
