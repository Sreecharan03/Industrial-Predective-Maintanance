"""Ingestion layer - validated typed time-series from any source."""

from senseminds.ingestion.base import IngestionError, TimeSeriesSource
from senseminds.ingestion.csv_source import ProcessedCsvSource
from senseminds.ingestion.db_reading_sink import DbReadingSink
from senseminds.ingestion.db_source import DbTimeSeriesSource
from senseminds.ingestion.melt import iter_readings
from senseminds.ingestion.models import IngestedSeries, IngestionManifest
from senseminds.ingestion.reading import (
    QualityFlag,
    Reading,
    ReadingValidation,
    ReadingValidationResult,
    RejectedReading,
)
from senseminds.ingestion.sink import ReadingSink
from senseminds.ingestion.unit_sensor import UnitSensorCatalog

__all__ = [
    "DbReadingSink",
    "DbTimeSeriesSource",
    "UnitSensorCatalog",
    "IngestedSeries",
    "IngestionError",
    "IngestionManifest",
    "ProcessedCsvSource",
    "QualityFlag",
    "Reading",
    "ReadingSink",
    "ReadingValidation",
    "ReadingValidationResult",
    "RejectedReading",
    "TimeSeriesSource",
    "iter_readings",
]
