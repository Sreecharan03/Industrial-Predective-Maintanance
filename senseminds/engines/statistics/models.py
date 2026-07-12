"""Statistics engine result models."""

from __future__ import annotations

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.results import EngineResult


class SensorStatistics(FrozenModel):
    """Full descriptive + spread statistics for one sensor.

    Optional numeric fields are None only when the sensor has no valid
    readings at all (a fully-empty channel) - never silently zero-filled.
    """

    sensor_key: str
    count: int = Field(ge=0, description="Valid (non-null) readings.")
    missing: int = Field(ge=0)
    missing_pct: float = Field(ge=0.0, le=100.0)
    unique: int = Field(ge=0)
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    variance: float | None = None
    p5: float | None = None
    p25: float | None = None
    p75: float | None = None
    p95: float | None = None
    iqr: float | None = Field(default=None, description="P75 - P25.")
    value_range: float | None = Field(default=None, description="max - min.")
    cv_pct: float | None = Field(default=None, description="Coefficient of variation, %.")
    iqr_outliers: int = Field(default=0, ge=0, description="Readings beyond 1.5*IQR of quartiles.")
    iqr_outlier_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class StatisticsResult(EngineResult):
    """Per-sensor engineering statistics for one unit (descriptive only)."""

    unit: str
    n_rows: int = Field(ge=0)
    sensors: tuple[SensorStatistics, ...]

    def sensor(self, key: str) -> SensorStatistics | None:
        return next((s for s in self.sensors if s.sensor_key == key), None)
