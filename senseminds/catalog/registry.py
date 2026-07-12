"""Asset catalog construction.

Builds typed domain `Asset` objects (with their `Sensor`s) and `Threshold`
objects from the reference table + the actual columns present in a unit's data.
Pure functions over an injected ``columns_by_unit`` mapping so the catalog can
be built in tests without touching disk; the CSV-header loader lives in the
ingestion layer.
"""

from __future__ import annotations

from senseminds.catalog import reference_data as ref
from senseminds.domain.entities import Asset, Sensor, Subsystem, Threshold
from senseminds.domain.enums import ThresholdStatus
from senseminds.domain.value_objects import EngineeringUnit
from senseminds.infrastructure.logging import get_logger

_log = get_logger(__name__)


class UnknownSensorColumnError(ValueError):
    """A data column has no catalog metadata - the catalog must be updated
    before that column can be ingested (fail loud rather than silently drop)."""


def build_asset(unit: str, columns: list[str], *, strict: bool = True) -> Asset:
    """Construct the typed Asset for one unit from its data columns.

    ``strict`` (default) raises on a sensor column with no catalog metadata;
    set False to skip-and-log instead (used only for exploratory tooling).
    """
    if unit not in ref.EQUIPMENT_CLASS_BY_UNIT:
        raise UnknownSensorColumnError(f"no catalog entry for unit {unit!r}")

    sensors: list[Sensor] = []
    for col in columns:
        if col in ref.NON_SENSOR_COLUMNS:
            continue
        meta = ref.sensor_metadata(col)
        if meta is None:
            if strict:
                raise UnknownSensorColumnError(
                    f"unit {unit!r} column {col!r} has no catalog metadata"
                )
            _log.warning("unknown_sensor_column", extra={"unit": unit, "column": col})
            continue
        display, sensor_type, unit_symbol, assumed = meta
        sensors.append(
            Sensor(
                key=ref.sensor_key(col),
                source_column=col,
                display_name=display,
                sensor_type=sensor_type,
                unit=EngineeringUnit(symbol=unit_symbol, assumed=assumed),
            )
        )
    return Asset(
        key=unit,
        display_name=unit,
        equipment_class=ref.EQUIPMENT_CLASS_BY_UNIT[unit],
        description=ref.UNIT_DESCRIPTION.get(unit, ""),
        sensors=tuple(sensors),
        subsystems=_build_subsystems(sensors),
    )


def _build_subsystems(sensors: list[Sensor]) -> tuple[Subsystem, ...]:
    """Group an asset's sensors into functional subsystems (for Health rollup)."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for sensor in sensors:
        key, display = ref.subsystem_for(sensor.source_column)
        grouped.setdefault((key, display), []).append(sensor.key)
    return tuple(
        Subsystem(key=key, display_name=display, sensor_keys=tuple(sensor_keys))
        for (key, display), sensor_keys in grouped.items()
    )


def build_catalog(
    columns_by_unit: dict[str, list[str]], *, strict: bool = True
) -> dict[str, Asset]:
    """Build the full asset catalog keyed by unit."""
    return {unit: build_asset(unit, cols, strict=strict) for unit, cols in columns_by_unit.items()}


def thresholds_for(unit: str, asset: Asset) -> dict[str, Threshold]:
    """Return a Threshold per sensor of the asset.

    Sensors with a supplied min/max get status AVAILABLE; every other sensor
    gets MISSING with no invented bounds (Phase-1 discipline). Sensors the
    supplied table doesn't cover but that belong to a thresholded unit are
    marked REQUIRES_MANUAL_VALIDATION rather than plain MISSING, matching the
    Threshold Mapping Report's language.
    """
    supplied = ref.THRESHOLDS.get(unit, {})
    unit_has_table = unit in ref.THRESHOLDS
    out: dict[str, Threshold] = {}
    for sensor in asset.sensors:
        if sensor.source_column in supplied:
            lo, hi = supplied[sensor.source_column]
            out[sensor.key] = Threshold(
                sensor_key=sensor.key,
                status=ThresholdStatus.AVAILABLE,
                minimum=lo,
                maximum=hi,
            )
        elif unit_has_table:
            out[sensor.key] = Threshold(
                sensor_key=sensor.key,
                status=ThresholdStatus.REQUIRES_MANUAL_VALIDATION,
                note="Unit has a supplied table but it does not cover this sensor.",
            )
        else:
            out[sensor.key] = Threshold(
                sensor_key=sensor.key,
                status=ThresholdStatus.MISSING,
                note="No threshold table supplied for this unit.",
            )
    return out
