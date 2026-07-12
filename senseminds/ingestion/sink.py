"""Reading sink port (ADR-019 D2).

The write-side counterpart to `TimeSeriesSource`: where validated readings are
persisted. An interface so ingestion is agnostic to the store; the TimescaleDB
adapter implements it now, a streaming/historian adapter can implement it later
without any change to ingestion or engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from senseminds.ingestion.reading import Reading


class ReadingSink(ABC):
    """Persist validated readings into the sensor-history store."""

    @abstractmethod
    def write(self, readings: Sequence[Reading]) -> int:
        """Persist readings idempotently; return the number submitted.

        Implementations upsert with conflict-ignore so re-submitting the same
        `(unit, sensor_key, time)` is a no-op (bootstrap/retry safe).
        """
