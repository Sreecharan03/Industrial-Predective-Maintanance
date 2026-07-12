"""Time-series source port.

Ingestion is defined as an interface so the platform is agnostic to where data
comes from. The processed-CSV adapter implements it now; a PDF-extraction
adapter and, later, live historian/OPC-UA/MQTT adapters implement the same
contract without any engine or use-case changing (ADR-004).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from senseminds.ingestion.models import IngestedSeries


class IngestionError(RuntimeError):
    """Raised when a source cannot produce a valid IngestedSeries."""


class TimeSeriesSource(ABC):
    """A source of validated per-unit time series."""

    @abstractmethod
    def available_units(self) -> list[str]:
        """Return the unit keys this source can provide."""

    @abstractmethod
    def load(self, unit: str) -> IngestedSeries:
        """Load and validate one unit's series. Raises IngestionError on failure."""
