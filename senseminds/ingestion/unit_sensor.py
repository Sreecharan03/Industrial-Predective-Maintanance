"""Per-unit sensor identity (ADR-019 D2).

Persists the exact `(sensor_key -> source_column, order)` mapping for each unit so
`DbTimeSeriesSource` can rebuild the *same* Asset `ProcessedCsvSource` produced.
The processed CSVs use stripped headers ("Oil Pressure") while the catalog's
canonical column carries the unit ("Oil Pressure (kg/cm2)"), and thresholds are
matched by source column - so the mapping is persisted, not re-derived, keeping
the reconstructed Asset (and every engine output) byte-identical.
"""

from __future__ import annotations

from sqlalchemy import text

from senseminds.domain.entities import Asset
from senseminds.infrastructure.db import SENSOR_HISTORY, Database

_UPSERT = text(
    """
    INSERT INTO sensor_history.unit_sensor (unit, sensor_key, source_column, ordinal)
    VALUES (:unit, :sensor_key, :source_column, :ordinal)
    ON CONFLICT (unit, sensor_key)
        DO UPDATE SET source_column = EXCLUDED.source_column, ordinal = EXCLUDED.ordinal
    """
)
_COLUMNS = text(
    "SELECT source_column FROM sensor_history.unit_sensor WHERE unit = :unit ORDER BY ordinal"
)


class UnitSensorCatalog:
    """Read/write the persisted per-unit sensor-column identity."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_asset(self, asset: Asset) -> None:
        """Persist an asset's sensor columns in their canonical (build) order."""
        rows = [
            {
                "unit": asset.key,
                "sensor_key": sensor.key,
                "source_column": sensor.source_column,
                "ordinal": ordinal,
            }
            for ordinal, sensor in enumerate(asset.sensors)
        ]
        if not rows:
            return
        with self._db.session(SENSOR_HISTORY) as session:
            session.execute(_UPSERT, rows)

    def source_columns(self, unit: str) -> list[str]:
        """The unit's source columns in order (empty if the unit is unknown)."""
        with self._db.session(SENSOR_HISTORY) as session:
            return [row[0] for row in session.execute(_COLUMNS, {"unit": unit})]
