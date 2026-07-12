"""Ingestion result models.

`IngestedSeries` is the typed hand-off from ingestion to the engines: the
asset it belongs to, a validated pandas frame (timestamp + one column per
sensor *key*), and a manifest describing what was loaded. It is a frozen
dataclass rather than a Pydantic model because it deliberately carries a
pandas DataFrame across the I/O boundary - pandas lives here and in the
engines, never in the domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from senseminds.domain.entities import Asset

TIMESTAMP_COLUMN = "timestamp"


@dataclass(frozen=True)
class IngestionManifest:
    """Provenance-grade description of one ingested unit."""

    unit: str
    source: str
    n_rows: int
    n_sensors: int
    start: datetime | None
    end: datetime | None
    sensor_keys: tuple[str, ...]


@dataclass(frozen=True)
class IngestedSeries:
    """An asset plus its validated time-series frame (sensor-key columns)."""

    asset: Asset
    frame: pd.DataFrame
    manifest: IngestionManifest

    def sensor_frame(self) -> pd.DataFrame:
        """The frame restricted to sensor-key columns (no timestamp)."""
        return self.frame[list(self.manifest.sensor_keys)]

    @property
    def timestamps(self) -> pd.Series:
        return self.frame[TIMESTAMP_COLUMN]
