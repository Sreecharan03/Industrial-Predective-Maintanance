"""Domain entities.

Objects with identity and a lifecycle: the physical asset hierarchy (Asset ->
Subsystem -> Sensor), the engineering concepts attached to them (Threshold,
OperatingState, Envelope, FailureMode), and the reasoning outputs (Finding,
HealthScore). Pure domain - no persistence, no framework, no pandas.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from senseminds.domain.enums import (
    EquipmentClass,
    OperatingStateLabel,
    SensorType,
    Severity,
    ThresholdStatus,
)
from senseminds.domain.value_objects import Confidence, EngineeringUnit, Evidence


class _Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sensor(_Entity):
    """A single measured channel on an asset."""

    key: str = Field(min_length=1, description="Stable machine key, e.g. 'oil_pressure_com1'.")
    source_column: str = Field(min_length=1, description="Original PDF/log-sheet column header.")
    display_name: str = Field(min_length=1)
    sensor_type: SensorType
    unit: EngineeringUnit


class Subsystem(_Entity):
    """A functional grouping of sensors within an asset (e.g. oil circuit)."""

    key: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    sensor_keys: tuple[str, ...] = Field(default_factory=tuple)


class Asset(_Entity):
    """A physical unit under monitoring (compressor, air plant, N2 plant)."""

    key: str = Field(min_length=1, description="Unit id, e.g. 'SC-126'.")
    display_name: str = Field(min_length=1)
    equipment_class: EquipmentClass
    description: str = Field(default="")
    subsystems: tuple[Subsystem, ...] = Field(default_factory=tuple)
    sensors: tuple[Sensor, ...] = Field(default_factory=tuple)

    def sensor(self, key: str) -> Sensor | None:
        return next((s for s in self.sensors if s.key == key), None)


class Threshold(_Entity):
    """A supplied engineering min/max for a sensor, with mapping status.

    Only SC-126 and SC-114 have supplied thresholds; every other sensor is
    MISSING and no min/max is invented (the Phase-1 discipline, encoded).
    """

    sensor_key: str = Field(min_length=1)
    status: ThresholdStatus
    minimum: float | None = None
    maximum: float | None = None
    note: str = Field(default="")


class OperatingState(_Entity):
    """One inferred operating band for an asset's activity indicator."""

    label: OperatingStateLabel
    indicator_key: str = Field(min_length=1, description="Sensor the state was segmented from.")
    lower: float | None = Field(default=None, description="Lower cut point (None = open below).")
    upper: float | None = Field(default=None, description="Upper cut point (None = open above).")


class Envelope(_Entity):
    """A sensor's historical operating envelope (percentile bands, not min/max)."""

    sensor_key: str = Field(min_length=1)
    p5: float
    p25: float
    p75: float
    p95: float
    mode_low: float | None = None
    mode_high: float | None = None


class FailureMode(_Entity):
    """A named degradation/fault mechanism reasoned about by rules and the KG."""

    key: str = Field(min_length=1, description="e.g. 'condenser_fouling'.")
    display_name: str = Field(min_length=1)
    description: str = Field(default="")


# NOTE: the canonical `Finding` now lives in `senseminds.findings` (the semantic
# layer, ADR-013). The earlier rule-only placeholder was removed when the
# generalized, immutable Finding contract superseded it.


class HealthScore(_Entity):
    """A deterministic health score for one level of the asset hierarchy.

    Carries the factors that produced it so it can be interrogated top-down
    (plant -> equipment -> subsystem -> sensor). Not ML-derived (ADR-008).
    """

    scope: str = Field(min_length=1, description="'sensor' | 'subsystem' | 'equipment' | 'plant'.")
    target_key: str = Field(min_length=1, description="Key of the scored entity.")
    score: float = Field(ge=0.0, le=100.0)
    severity: Severity
    confidence: Confidence | None = Field(
        default=None, description="How much to trust this score (from sensor reliability)."
    )
    contributing_factors: tuple[str, ...] = Field(default_factory=tuple)
    evidence: tuple[Evidence, ...] = Field(default_factory=tuple)
