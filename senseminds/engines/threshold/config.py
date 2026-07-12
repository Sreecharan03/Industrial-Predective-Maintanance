"""Threshold specification assembly from the catalog.

Turns the catalog's raw threshold data (operating ranges + protection
setpoints) into a typed `ThresholdSpec` + `ThresholdStatus` per sensor. This
is the boundary between catalog *data* and threshold *evaluation*: the numbers
live in the catalog (single source of truth for values); the engine owns
evaluation. No threshold is invented for a sensor the catalog does not cover.
"""

from __future__ import annotations

from senseminds.catalog import reference_data as ref
from senseminds.domain.entities import Sensor
from senseminds.domain.enums import ThresholdStatus
from senseminds.engines.threshold.models import (
    ProtectionSetpoint,
    ThresholdBand,
    ThresholdSpec,
)


def threshold_spec_for(unit: str, sensor: Sensor) -> tuple[ThresholdStatus, ThresholdSpec]:
    """Return the (status, spec) for a sensor, following Phase-1 discipline.

    - operating range supplied  -> AVAILABLE (+ any protection setpoints)
    - unit has a table but not this sensor -> REQUIRES_MANUAL_VALIDATION
    - unit has no table at all   -> MISSING
    """
    supplied = ref.THRESHOLDS.get(unit, {})
    unit_has_table = unit in ref.THRESHOLDS
    col = sensor.source_column

    if col in supplied:
        low, high = supplied[col]
        prot = ref.PROTECTION_SETPOINTS.get(unit, {}).get(col, [])
        protection = tuple(
            ProtectionSetpoint(name=name, level=level, direction="high") for name, level in prot
        )
        spec = ThresholdSpec(operating=ThresholdBand(low=low, high=high), protection=protection)
        return ThresholdStatus.AVAILABLE, spec

    if unit_has_table:
        return ThresholdStatus.REQUIRES_MANUAL_VALIDATION, ThresholdSpec()
    return ThresholdStatus.MISSING, ThresholdSpec()
