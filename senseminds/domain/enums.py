"""Domain enumerations.

Closed vocabularies for equipment, sensors, states, and severity. Kept in the
domain layer because they encode engineering meaning, not implementation
detail. Values mirror the taxonomy established in the Phase-1/2 analysis
(SC-* refrigeration screw compressors; COM-*/NP-* utility air + N2 plant).
"""

from __future__ import annotations

from enum import StrEnum


class EquipmentClass(StrEnum):
    """The kind of industrial asset, which determines applicable thresholds."""

    REFRIGERATION_SCREW_COMPRESSOR = "refrigeration_screw_compressor"
    UTILITY_AIR_COMPRESSOR = "utility_air_compressor"
    NITROGEN_PSA_PLANT = "nitrogen_psa_plant"


class SensorType(StrEnum):
    """Physical quantity a sensor measures."""

    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    ELECTRICAL_CURRENT = "electrical_current"
    LOAD = "load"
    FLOW = "flow"
    GAS_PURITY = "gas_purity"


class OperatingStateLabel(StrEnum):
    """Operating states inferred by the Operating State Engine (step6).

    Not hardcoded thresholds - these are the label vocabulary the density-valley
    segmentation maps its discovered bands onto.
    """

    MACHINE_OFF = "machine_off"
    STARTUP_PULLDOWN = "startup_pulldown"
    PARTIAL_LOAD = "partial_load"
    FULL_LOAD_STABLE = "full_load_stable"
    HIGH_LOAD_VARIABLE = "high_load_variable"
    LOAD_TRANSITION = "load_transition"
    UNLOADING_SHUTDOWN = "unloading_shutdown"
    CONTINUOUS_STABLE = "continuous_stable"


class Severity(StrEnum):
    """Ordered severity for findings and health degradation."""

    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"ok": 0, "info": 1, "warning": 2, "critical": 3}[self.value]


class ThresholdStatus(StrEnum):
    """Result of mapping a sensor to a supplied threshold (step3)."""

    AVAILABLE = "available"
    MISSING = "missing"
    CANNOT_MAP = "cannot_map"
    REQUIRES_MANUAL_VALIDATION = "requires_manual_validation"
