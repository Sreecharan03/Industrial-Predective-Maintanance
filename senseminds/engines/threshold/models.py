"""Threshold engine result models.

Immutable public contract. The Threshold Engine is the single source of truth
for threshold evaluation in SenseMinds - no other engine compares sensor
values to thresholds; they consume ThresholdResult. Threshold levels are
modelled separately (operating range vs escalating protection setpoints) and
partial definitions are supported: a sensor may have an operating range only,
protection setpoints too, or no threshold at all.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from senseminds.domain.base import FrozenModel
from senseminds.domain.enums import Severity, ThresholdStatus
from senseminds.domain.results import EngineResult
from senseminds.domain.value_objects import Confidence


class ThresholdState(StrEnum):
    """State of a single evaluated reading relative to its thresholds."""

    WITHIN_RANGE = "within_range"
    OUTSIDE_OPERATING = "outside_operating"
    CRITICAL = "critical"
    TRIP = "trip"
    UNKNOWN = "unknown"  # no threshold, or no reading to evaluate


class ThresholdBand(FrozenModel):
    """A range with optional bounds (an open side means 'no limit that way')."""

    low: float | None = None
    high: float | None = None

    @model_validator(mode="after")
    def _ordered(self) -> ThresholdBand:
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"threshold band low ({self.low}) exceeds high ({self.high})")
        return self


class ProtectionSetpoint(FrozenModel):
    """An escalating protection limit above/below the operating range."""

    name: str
    level: float
    direction: str = Field(default="high", description="'high' or 'low' side.")


class ThresholdSpec(FrozenModel):
    """The thresholds defined for a sensor (any part may be absent)."""

    operating: ThresholdBand | None = None
    protection: tuple[ProtectionSetpoint, ...] = Field(default_factory=tuple)


class ProtectionCount(FrozenModel):
    """How often history reached a protection setpoint."""

    name: str
    level: float
    direction: str
    count: int = Field(ge=0)
    pct_of_readings: float = Field(ge=0.0, le=100.0)


class ThresholdHistory(FrozenModel):
    """Historical breach summary over all valid readings for a sensor."""

    n_evaluated: int = Field(ge=0)
    n_within_operating: int = Field(ge=0)
    n_outside_operating: int = Field(ge=0)
    pct_within: float = Field(ge=0.0, le=100.0)
    pct_outside: float = Field(ge=0.0, le=100.0)
    protection_counts: tuple[ProtectionCount, ...] = Field(default_factory=tuple)


class ThresholdEvidence(FrozenModel):
    """Why a threshold verdict holds - quotable by the future LLM."""

    threshold_evaluated: str
    observed_value: float | None
    threshold_value: str
    interpretation: str
    historical_context: str = Field(
        default="",
        description="Where the threshold sits relative to historically typical operation "
        "(from the Operating Envelope) - distinguishes engineering-limit violations from "
        "readings that are simply outside a threshold the machine never operates within.",
    )
    confidence: Confidence
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)


class SensorThresholdResult(FrozenModel):
    """Threshold verdict for one sensor."""

    sensor_key: str
    status: ThresholdStatus
    spec: ThresholdSpec
    latest_value: float | None
    current_state: ThresholdState
    severity: Severity
    active_violations: tuple[str, ...] = Field(default_factory=tuple)
    history: ThresholdHistory | None = None
    evidence: ThresholdEvidence


class ThresholdResult(EngineResult):
    """Threshold verdicts for every sensor of a unit (immutable)."""

    unit: str
    sensors: tuple[SensorThresholdResult, ...]

    def sensor(self, key: str) -> SensorThresholdResult | None:
        return next((s for s in self.sensors if s.sensor_key == key), None)
