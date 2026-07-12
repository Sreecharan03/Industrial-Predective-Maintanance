"""TimescaleDB time-series source (ADR-019 D2).

Implements the existing `TimeSeriesSource` port by reading persisted readings
from `sensor_history` and reconstructing the exact `IngestedSeries` frame the
engines already consume (timestamp + one column per sensor key). Engines never
learn the data now comes from a database - the pandas boundary is preserved.

After bootstrap this is the *only* source engines read from; CSV is bootstrap-
only.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from senseminds.catalog import build_asset
from senseminds.infrastructure.db import SENSOR_HISTORY, Database
from senseminds.ingestion.base import IngestionError, TimeSeriesSource
from senseminds.ingestion.models import TIMESTAMP_COLUMN, IngestedSeries, IngestionManifest
from senseminds.ingestion.unit_sensor import UnitSensorCatalog

_UNITS = text("SELECT DISTINCT unit FROM sensor_history.sensor_reading ORDER BY unit")
_READINGS = text(
    """
    SELECT time, sensor_key, value
    FROM sensor_history.sensor_reading
    WHERE unit = :unit
    ORDER BY time
    """
)


class DbTimeSeriesSource(TimeSeriesSource):
    """Load a unit's validated series from the TimescaleDB sensor history."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._sensors = UnitSensorCatalog(db)

    def available_units(self) -> list[str]:
        with self._db.session(SENSOR_HISTORY) as session:
            return [row[0] for row in session.execute(_UNITS)]

    def load(self, unit: str) -> IngestedSeries:
        with self._db.session(SENSOR_HISTORY) as session:
            session.execute(text("SET TIME ZONE 'UTC'"))
            rows = session.execute(_READINGS, {"unit": unit}).all()
        if not rows:
            raise IngestionError(f"no persisted readings for unit {unit!r}")

        long = pd.DataFrame(rows, columns=[TIMESTAMP_COLUMN, "sensor_key", "value"])
        wide = long.pivot(index=TIMESTAMP_COLUMN, columns="sensor_key", values="value")

        # Rebuild the *same* Asset ProcessedCsvSource produced from the persisted
        # per-unit source columns (exact strings, exact order), so sensors,
        # subsystems, thresholds AND the frame's column order are byte-identical.
        columns = self._sensors.source_columns(unit)
        if not columns:
            raise IngestionError(f"no persisted sensor identity for unit {unit!r}")
        asset = build_asset(unit, columns)

        # Column order follows the canonical catalog order (present keys only),
        # so the frame matches what ProcessedCsvSource produced.
        present = [s.key for s in asset.sensors if s.key in wide.columns]
        wide = wide.reindex(columns=present).astype("float64")
        wide.columns.name = None  # drop the pivot's 'sensor_key' axis label

        frame = wide.reset_index()
        # Stored as UTC; drop tz to match the CSV source's naive timestamps.
        frame[TIMESTAMP_COLUMN] = (
            pd.to_datetime(frame[TIMESTAMP_COLUMN], utc=True).dt.tz_localize(None)
        )
        frame = frame.sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)

        manifest = IngestionManifest(
            unit=unit,
            source="timescaledb",
            n_rows=len(frame),
            n_sensors=len(present),
            start=frame[TIMESTAMP_COLUMN].min() if len(frame) else None,
            end=frame[TIMESTAMP_COLUMN].max() if len(frame) else None,
            sensor_keys=tuple(present),
        )
        return IngestedSeries(asset=asset, frame=frame, manifest=manifest)
