"""Asset catalog - the platform's typed registry of units, sensors, thresholds."""

from senseminds.catalog.reference_data import (
    EQUIPMENT_CLASS_BY_UNIT,
    NON_SENSOR_COLUMNS,
    sensor_key,
)
from senseminds.catalog.registry import (
    UnknownSensorColumnError,
    build_asset,
    build_catalog,
    thresholds_for,
)

__all__ = [
    "EQUIPMENT_CLASS_BY_UNIT",
    "NON_SENSOR_COLUMNS",
    "UnknownSensorColumnError",
    "build_asset",
    "build_catalog",
    "sensor_key",
    "thresholds_for",
]
