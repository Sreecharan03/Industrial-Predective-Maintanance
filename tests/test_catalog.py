"""Catalog: typed assets, sensor keys, and threshold discipline."""

from __future__ import annotations

import pytest
from senseminds.catalog import build_asset, sensor_key, thresholds_for
from senseminds.catalog.registry import UnknownSensorColumnError
from senseminds.domain.enums import SensorType, ThresholdStatus

SC126_COLUMNS = [
    "Date", "Time", "Suction Pressure", "Discharge Pressure", "Oil Pressure",
    "Suction Temp", "Oil Temp", "Discharge Temp", "Condenser Entering Temp",
    "Condenser Leaving Temp", "Running Amperes", "Loading Percentage",
    "Remarks", "source_file", "timestamp",
]


def test_sensor_key_slugifies_headers() -> None:
    assert sensor_key("Discharge Pressure Com1") == "discharge_pressure_com1"
    assert sensor_key("Oil Pressure (kg/cm2)") == "oil_pressure"
    assert sensor_key("ADU1 Temp (C)") == "adu1_temp"
    assert sensor_key("O2 %") == "o2_pct"


def test_build_asset_sc126() -> None:
    asset = build_asset("SC-126", SC126_COLUMNS)
    assert len(asset.sensors) == 10  # 10 numeric sensors, non-sensor cols excluded
    sp = asset.sensor("suction_pressure")
    assert sp is not None
    assert sp.sensor_type is SensorType.PRESSURE
    assert sp.unit.symbol == "kg/cm2"
    assert asset.sensor("running_amperes").sensor_type is SensorType.ELECTRICAL_CURRENT


def test_unknown_column_raises_in_strict_mode() -> None:
    with pytest.raises(UnknownSensorColumnError):
        build_asset("SC-126", ["timestamp", "Mystery Sensor"])


def test_thresholds_status_discipline() -> None:
    asset = build_asset("SC-126", SC126_COLUMNS)
    th = thresholds_for("SC-126", asset)
    # supplied threshold
    assert th["suction_pressure"].status is ThresholdStatus.AVAILABLE
    assert (th["suction_pressure"].minimum, th["suction_pressure"].maximum) == (10, 30)
    # present in a thresholded unit but not covered by the supplied table
    assert th["suction_temp"].status is ThresholdStatus.REQUIRES_MANUAL_VALIDATION


def test_thresholds_missing_for_utility_unit() -> None:
    cols = ["timestamp", "Oil Pressure (kg/cm2)", "Discharge Temp (C)", "Receiver Pressure"]
    asset = build_asset("COM-102", cols)
    th = thresholds_for("COM-102", asset)
    assert all(t.status is ThresholdStatus.MISSING for t in th.values())
    assert all(t.minimum is None and t.maximum is None for t in th.values())
