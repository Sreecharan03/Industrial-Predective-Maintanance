"""Asset-catalog reference data.

The platform's own source of truth for what each unit is, which sensors it
carries, their engineering type/unit, and any supplied threshold. Ported
faithfully from the Phase-1 analysis (``Datasets/scripts/common.py``) so the
platform no longer depends on the analysis scratch. This table later seeds the
Knowledge Graph (Milestone 3).

Discipline preserved from Phase 1: thresholds exist ONLY for SC-126 and SC-114
(the two units with supplied tables); nothing is invented for any other unit.
"""

from __future__ import annotations

import re

from senseminds.domain.enums import EquipmentClass, SensorType

_SENSOR_TYPE_MAP: dict[str, SensorType] = {
    "Pressure": SensorType.PRESSURE,
    "Temperature": SensorType.TEMPERATURE,
    "Electrical Current": SensorType.ELECTRICAL_CURRENT,
    "Load": SensorType.LOAD,
    "Flow": SensorType.FLOW,
    "Gas Purity": SensorType.GAS_PURITY,
}

EQUIPMENT_CLASS_BY_UNIT: dict[str, EquipmentClass] = {
    "SC-126": EquipmentClass.REFRIGERATION_SCREW_COMPRESSOR,
    "SC-114": EquipmentClass.REFRIGERATION_SCREW_COMPRESSOR,
    "SC-104": EquipmentClass.REFRIGERATION_SCREW_COMPRESSOR,
    "COM-102": EquipmentClass.UTILITY_AIR_COMPRESSOR,
    "COM-110": EquipmentClass.UTILITY_AIR_COMPRESSOR,
    "COM103 & NP102": EquipmentClass.NITROGEN_PSA_PLANT,
}

_SC_300TR = (
    "Refrigeration screw compressor (300 TR, +5C, B/S chiller) - twin compressor (Com1/Com2)"
)

UNIT_DESCRIPTION: dict[str, str] = {
    "SC-126": "Refrigeration screw compressor (91 TR, -20C, Voltas chiller) - single compressor",
    "SC-114": _SC_300TR,
    "SC-104": _SC_300TR,
    "COM-102": "Utility air compressor + twin-tower air dryer (ADU1/ADU2)",
    "COM-110": (
        "Utility air compressor + twin-tower air dryer (ADU1/ADU2), with cooling water circuit"
    ),
    "COM103 & NP102": "Utility air compressor + Nitrogen (PSA) generation plant",
}

# source column -> (display name, sensor-type key, unit symbol, unit-assumed?)
# Faithful port of common.SENSOR_META. A unit symbol suffixed "(assumed)" in
# the source is represented here by the assumed=True flag.
_SENSOR_META: dict[str, tuple[str, str, str, bool]] = {
    # SC-126
    "Suction Pressure": ("Suction Pressure", "Pressure", "kg/cm2", False),
    "Discharge Pressure": ("Discharge Pressure", "Pressure", "kg/cm2", False),
    "Oil Pressure": ("Oil Pressure", "Pressure", "kg/cm2", False),
    "Suction Temp": ("Suction Temperature", "Temperature", "C", False),
    "Oil Temp": ("Oil Temperature", "Temperature", "C", False),
    "Discharge Temp": ("Discharge Temperature", "Temperature", "C", False),
    "Condenser Entering Temp": ("Condenser Entering Temperature", "Temperature", "C", False),
    "Condenser Leaving Temp": ("Condenser Leaving Temperature", "Temperature", "C", False),
    "Running Amperes": ("Running Amperes", "Electrical Current", "A", False),
    "Loading Percentage": ("Loading Percentage", "Load", "%", False),
    # SC-104 / SC-114 (Com1/Com2)
    "Loading Percentage Com1": ("Loading Percentage - Compressor 1", "Load", "%", False),
    "Loading Percentage Com2": ("Loading Percentage - Compressor 2", "Load", "%", False),
    "Suction Pressure Com1": ("Suction Pressure - Compressor 1", "Pressure", "kg/cm2", False),
    "Suction Pressure Com2": ("Suction Pressure - Compressor 2", "Pressure", "kg/cm2", False),
    "Discharge Pressure Com1": ("Discharge Pressure - Compressor 1", "Pressure", "kg/cm2", False),
    "Discharge Pressure Com2": ("Discharge Pressure - Compressor 2", "Pressure", "kg/cm2", False),
    "Oil Pressure Com1": ("Oil Pressure - Compressor 1", "Pressure", "kg/cm2", False),
    "Oil Pressure Com2": ("Oil Pressure - Compressor 2", "Pressure", "kg/cm2", False),
    "Suction Temp Com1": ("Suction Temperature - Compressor 1", "Temperature", "C", False),
    "Suction Temp Com2": ("Suction Temperature - Compressor 2", "Temperature", "C", False),
    "Discharge Temp Com1": ("Discharge Temperature - Compressor 1", "Temperature", "C", False),
    "Discharge Temp Com2": ("Discharge Temperature - Compressor 2", "Temperature", "C", False),
    "Running Amperes Com1": ("Running Amperes - Compressor 1", "Electrical Current", "A", False),
    "Running Amperes Com2": ("Running Amperes - Compressor 2", "Electrical Current", "A", False),
    "Evaporator Leaving Temp": ("Evaporator Leaving Temperature", "Temperature", "C", False),
    "Evaporator Entering Temp": ("Evaporator Entering Temperature", "Temperature", "C", False),
    # COM-102 / COM-110 (air compressors)
    "Oil Pressure (kg/cm2)": ("Oil Pressure", "Pressure", "kg/cm2", False),
    "Discharge Temp (C)": ("Discharge Temperature", "Temperature", "C", False),
    "ADU1 Temp (C)": ("Air Dryer Unit 1 - Bed Temperature", "Temperature", "C", False),
    "ADU1 Pressure (kg/cm2)": ("Air Dryer Unit 1 - Tower Pressure", "Pressure", "kg/cm2", False),
    "ADU2 Temp (C)": ("Air Dryer Unit 2 - Bed Temperature", "Temperature", "C", False),
    "ADU2 Pressure (kg/cm2)": ("Air Dryer Unit 2 - Tower Pressure", "Pressure", "kg/cm2", False),
    "Receiver Pressure": ("Compressed Air Receiver Pressure", "Pressure", "kg/cm2", True),
    "Receiver Pressure (kg/cm2)": ("Compressed Air Receiver Pressure", "Pressure", "kg/cm2", False),
    "Dew Point Temperature": ("Dew Point Temperature", "Temperature", "C", True),
    "Cooling Water Pressure Inlet (kg/cm2)": (
        "Cooling Water Pressure - Inlet", "Pressure", "kg/cm2", False),
    "Cooling Water Pressure Outlet (kg/cm2)": (
        "Cooling Water Pressure - Outlet", "Pressure", "kg/cm2", False),
    # COM103 & NP102 (air + nitrogen plant)
    "ADU1 Pressure": ("Air Dryer Unit 1 Pressure", "Pressure", "kg/cm2", True),
    "ADU2 Pressure": ("Air Dryer Unit 2 Pressure", "Pressure", "kg/cm2", True),
    "Pressure on PSA-1 Tower": ("PSA Tower 1 Pressure", "Pressure", "kg/cm2", True),
    "Pressure on PSA-2 Tower": ("PSA Tower 2 Pressure", "Pressure", "kg/cm2", True),
    "Pressure on Surge Tank": ("Surge Tank Pressure", "Pressure", "kg/cm2", True),
    "Nitrogen Flow Rate (Nm3/Hr)": ("Nitrogen Product Flow Rate", "Flow", "Nm3/hr", False),
    "O2 %": ("Residual Oxygen Concentration", "Gas Purity", "%", False),
    "Nitrogen Storage Tank Pressure": (
        "Nitrogen Storage Tank Pressure", "Pressure", "kg/cm2", True),
    "Micron Filter Pressure": ("Micron Filter Line Pressure", "Pressure", "kg/cm2", True),
}

# Supplied thresholds - ONLY SC-126 and SC-114. Keyed by source column.
THRESHOLDS: dict[str, dict[str, tuple[float, float]]] = {
    "SC-126": {
        "Suction Pressure": (10, 30),
        "Discharge Pressure": (235, 247),
        "Oil Pressure": (190, 225),
        "Oil Temp": (50, 65),
        "Discharge Temp": (0, 90),
        "Running Amperes": (0, 250),
        "Loading Percentage": (0, 100),
    },
    "SC-114": {
        "Suction Pressure Com1": (30, 48),
        "Suction Pressure Com2": (30, 48),
        "Oil Pressure Com1": (150, 165),
        "Oil Pressure Com2": (150, 165),
        "Discharge Pressure Com1": (150, 165),
        "Discharge Pressure Com2": (150, 165),
        "Evaporator Leaving Temp": (6, 8),
        "Evaporator Entering Temp": (6, 8),
        "Running Amperes Com1": (0, 185),
        "Running Amperes Com2": (0, 185),
        "Discharge Temp Com1": (0, 76),
        "Discharge Temp Com2": (0, 76),
        "Loading Percentage Com1": (0, 100),
        "Loading Percentage Com2": (0, 100),
    },
}

# Protection / interlock setpoints supplied ALONGSIDE the operating range -
# escalating upper limits above the normal operating max. Keyed by unit ->
# source column -> [(name, level)], all high-side (readings at/above concern).
# Supplied only for SC-126 discharge pressure (Phase-1 protection notes:
# critical ~= 280, unload ~= 285, trip ~= 297). Not invented for any other
# sensor/unit.
PROTECTION_SETPOINTS: dict[str, dict[str, list[tuple[str, float]]]] = {
    "SC-126": {
        "Discharge Pressure": [("critical", 280.0), ("unload", 285.0), ("trip", 297.0)],
    },
}

# Non-sensor columns present in every processed CSV.
NON_SENSOR_COLUMNS: frozenset[str] = frozenset(
    {"Date", "Time", "Remarks", "source_file", "timestamp"}
)

# Subsystem classification: each sensor is assigned to a functional subsystem by
# the first matching keyword in its source column. Ordered so specific circuits
# (oil, condenser, ...) win before the generic compression core. Health scoring
# rolls sensor health up to these subsystems (ADR-011 finding 1.2).
_SUBSYSTEM_RULES: list[tuple[str, str, str]] = [
    ("oil", "oil_system", "Oil System"),
    ("condenser", "condenser", "Condenser Circuit"),
    ("evaporator", "evaporator", "Evaporator Circuit"),
    ("adu", "air_dryer", "Air Dryer"),
    ("dew point", "air_dryer", "Air Dryer"),
    ("cooling water", "cooling_water", "Cooling Water Circuit"),
    ("psa", "nitrogen_generation", "Nitrogen Generation"),
    ("nitrogen", "nitrogen_generation", "Nitrogen Generation"),
    ("o2", "nitrogen_generation", "Nitrogen Generation"),
    ("surge", "nitrogen_generation", "Nitrogen Generation"),
    ("micron", "air_supply", "Compressed Air Supply"),
    ("receiver", "air_supply", "Compressed Air Supply"),
    ("suction", "compression", "Compression"),
    ("discharge", "compression", "Compression"),
    ("loading", "compression", "Compression"),
    ("amperes", "compression", "Compression"),
    ("running", "compression", "Compression"),
]


def subsystem_for(source_column: str) -> tuple[str, str]:
    """Return (subsystem_key, display_name) for a sensor's source column."""
    lname = source_column.lower()
    for keyword, key, display in _SUBSYSTEM_RULES:
        if keyword in lname:
            return key, display
    return "general", "General"


def sensor_key(source_column: str) -> str:
    """Derive a stable machine key from a source column header.

    Strips the parenthetical unit group, maps '%' to 'pct', and slugifies:
    ``"ADU1 Temp (C)" -> "adu1_temp"``, ``"O2 %" -> "o2_pct"``,
    ``"Discharge Pressure Com1" -> "discharge_pressure_com1"``.
    """
    text = re.sub(r"\([^)]*\)", " ", source_column)  # drop "(kg/cm2)", "(C)", ...
    text = text.replace("%", " pct ")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def sensor_metadata(source_column: str) -> tuple[str, SensorType, str, bool] | None:
    """Return (display_name, SensorType, unit_symbol, unit_assumed) or None."""
    meta = _SENSOR_META.get(source_column)
    if meta is None:
        return None
    display, type_key, unit_symbol, assumed = meta
    return display, _SENSOR_TYPE_MAP[type_key], unit_symbol, assumed
