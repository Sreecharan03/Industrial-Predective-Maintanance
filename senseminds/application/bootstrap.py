"""CSV → TimescaleDB bootstrap (ADR-019 D2).

A one-shot, idempotent loader: read each processed CSV via the existing
`ProcessedCsvSource`, melt to readings, validate, and persist through
`DbReadingSink`. CSV is used **only** here; after bootstrap every reader uses
`DbTimeSeriesSource`. Re-running is safe (ON CONFLICT DO NOTHING).

This is a composition-root concern (it wires ingestion + infrastructure), hence
it lives in the application layer, not inside a pure inner module.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from senseminds.config import Settings, get_settings
from senseminds.infrastructure.db import Database, build_database
from senseminds.infrastructure.logging import configure_logging, get_logger
from senseminds.ingestion import ProcessedCsvSource
from senseminds.ingestion.db_reading_sink import DbReadingSink
from senseminds.ingestion.melt import iter_readings
from senseminds.ingestion.reading import ReadingValidation
from senseminds.ingestion.unit_sensor import UnitSensorCatalog

_log = get_logger(__name__)


def bootstrap_units(
    db: Database, processed_dir: Path, units: Sequence[str] | None = None
) -> dict[str, int]:
    """Load the named units (or all available) from CSV into sensor history."""
    csv = ProcessedCsvSource(processed_dir)
    sink = DbReadingSink(db)
    sensors = UnitSensorCatalog(db)
    targets = list(units) if units is not None else csv.available_units()

    written: dict[str, int] = {}
    for unit in targets:
        series = csv.load(unit)
        sensors.upsert_asset(series.asset)
        outcome = ReadingValidation(unit).validate(iter_readings(series))
        count = sink.write(outcome.accepted)
        written[unit] = count
        _log.info(
            "unit_bootstrapped",
            extra={"unit": unit, "written": count, "rejected": len(outcome.rejected)},
        )
    return written


def main(settings: Settings | None = None) -> None:  # pragma: no cover - CLI entrypoint
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = build_database(settings)
    try:
        bootstrap_units(db, settings.legacy_reports_root / "processed")
    finally:
        db.dispose()


if __name__ == "__main__":  # pragma: no cover
    main()
