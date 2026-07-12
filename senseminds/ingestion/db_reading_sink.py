"""TimescaleDB reading sink (ADR-019 D2).

Persists validated readings into `sensor_history.sensor_reading` with
`ON CONFLICT DO NOTHING` (idempotent: re-running the bootstrap or retrying a
batch inserts nothing new) and advances the per-unit ingest watermark - both in
one transaction (the ADR-019 §7 ingestion boundary). Lives in ingestion beside
`ProcessedCsvSource`; depends only on the infrastructure DB seam, so no package
cycle is introduced.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import batched

from sqlalchemy import text

from senseminds.infrastructure.db import SENSOR_HISTORY, Database
from senseminds.infrastructure.logging import get_logger
from senseminds.ingestion.reading import Reading
from senseminds.ingestion.sink import ReadingSink

_log = get_logger(__name__)

_INSERT = text(
    """
    INSERT INTO sensor_history.sensor_reading
        (time, unit, sensor_key, value, quality, source)
    VALUES (:time, :unit, :sensor_key, :value, :quality, :source)
    ON CONFLICT (unit, sensor_key, time) DO NOTHING
    """
)
_WATERMARK = text(
    """
    INSERT INTO sensor_history.ingest_watermark (unit, last_time)
    VALUES (:unit, :last_time)
    ON CONFLICT (unit) DO UPDATE
        SET last_time = GREATEST(sensor_history.ingest_watermark.last_time,
                                 EXCLUDED.last_time)
    """
)


class DbReadingSink(ReadingSink):
    """Persist readings into the TimescaleDB hypertable."""

    def __init__(self, db: Database, chunk_size: int = 20_000) -> None:
        self._db = db
        self._chunk = chunk_size

    def write(self, readings: Sequence[Reading]) -> int:
        if not readings:
            return 0
        with self._db.session(SENSOR_HISTORY) as session:
            # Interpret naive timestamps as UTC on both write and read so the
            # round-trip preserves the exact wall-clock value (parity).
            session.execute(text("SET TIME ZONE 'UTC'"))
            for chunk in batched(readings, self._chunk):
                session.execute(
                    _INSERT,
                    [
                        {
                            "time": r.time,
                            "unit": r.unit,
                            "sensor_key": r.sensor_key,
                            "value": r.value,
                            "quality": int(r.quality),
                            "source": r.source,
                        }
                        for r in chunk
                    ],
                )
            last_time = max(r.time for r in readings)
            session.execute(_WATERMARK, {"unit": readings[0].unit, "last_time": last_time})
        _log.info(
            "readings_written",
            extra={"unit": readings[0].unit, "count": len(readings)},
        )
        return len(readings)
