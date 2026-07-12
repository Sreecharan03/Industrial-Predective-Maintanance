"""Quality-gate result models."""

from __future__ import annotations

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.results import EngineResult


class SensorQuality(FrozenModel):
    """Per-sensor quality metrics for one unit."""

    sensor_key: str
    n_valid: int = Field(ge=0)
    n_missing: int = Field(ge=0)
    missing_pct: float = Field(ge=0.0, le=100.0)
    n_negative: int = Field(ge=0, description="Negative readings for pressure/current/flow.")
    n_out_of_range: int = Field(ge=0, description="Readings outside 0-100 for load/purity.")
    fault_code_value: float | None = Field(
        default=None, description="Repeated fixed value flagged as a likely transducer fault code."
    )
    fault_code_count: int = Field(default=0, ge=0)
    longest_flatline_run: int = Field(ge=0, description="Longest run of identical readings.")


class QualityResult(EngineResult):
    """Unit-level data-quality assessment (descriptive, advisory - not a veto).

    Reproduces the Phase-1 Data Quality checks as a typed artifact: per-sensor
    completeness + physical-validity + fault-code + flatline, plus unit-level
    timestamp integrity and empty-column detection.
    """

    unit: str
    n_rows: int = Field(ge=0)
    sensors: tuple[SensorQuality, ...]
    n_duplicate_timestamps: int = Field(ge=0)
    n_gaps: int = Field(ge=0, description="Inter-reading gaps exceeding the gap threshold.")
    largest_gap_hours: float | None = Field(default=None, ge=0.0)
    empty_columns: tuple[str, ...] = Field(default_factory=tuple)

    def sensor(self, key: str) -> SensorQuality | None:
        return next((s for s in self.sensors if s.sensor_key == key), None)
