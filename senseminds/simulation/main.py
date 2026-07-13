"""Simulator entrypoint: python -m senseminds.simulation.main

Seeds a back-filled 30-second dataset for every machine, then feeds one new row
per machine every 30 seconds and re-analyses just after each tick.
"""

from __future__ import annotations

from senseminds.catalog.reference_data import PROTECTION_SETPOINTS, THRESHOLDS
from senseminds.config import Settings, get_settings
from senseminds.infrastructure.db import build_database
from senseminds.infrastructure.logging import configure_logging, get_logger
from senseminds.simulation.generator import Drift
from senseminds.simulation.live import LiveSimulator, SimulatorConfig
from senseminds.simulation.profiles import profile_unit

_log = get_logger(__name__)


def build_drift(settings: Settings) -> Drift | None:
    """Ramp the chosen sensor up past a limit the platform will actually act on.

    The platform is deliberately conservative: a plain operating-range excursion
    raises nothing, because a mis-set band is not a fault. It raises a CRITICAL
    finding when a **protection setpoint** is breached. So the drift targets a
    protection setpoint when the sensor has one — for SC-126 that is discharge
    pressure, whose rise is what condenser fouling / non-condensables really look
    like. Falling back to the operating band only if no setpoints exist.
    """
    unit, column = settings.sim_drift_unit, settings.sim_drift_column
    if not unit or not column:
        return None

    profiles, _ = profile_unit(settings.legacy_reports_root / "processed", unit)
    base = next((p.base for p in profiles if p.source_column == column), None)
    if base is None:
        _log.warning("simulator_drift_unknown_sensor",
                     extra={"unit": unit, "column": column})
        return None

    setpoints = dict(PROTECTION_SETPOINTS.get(unit, {}).get(column, []))
    if "critical" in setpoints:
        critical = float(setpoints["critical"])
        trip = float(setpoints.get("trip", critical * 1.05))
        target = critical + 0.2 * (trip - critical)  # clearly past CRITICAL, below TRIP
        _log.info("simulator_drift", extra={
            "unit": unit, "column": column, "normal": round(base, 2),
            "critical_setpoint": critical, "target": round(target, 2),
            "ramp_minutes": settings.sim_drift_ramp_minutes})
        return Drift(unit=unit, source_column=column, target=target,
                     ramp_minutes=settings.sim_drift_ramp_minutes)

    band = THRESHOLDS.get(unit, {}).get(column)
    if band is None or not (band[0] <= base <= band[1]):
        _log.warning("simulator_drift_skipped", extra={"unit": unit, "column": column})
        return None
    low, high = band
    target = high + 0.35 * (high - base)
    _log.info("simulator_drift", extra={
        "unit": unit, "column": column, "normal": round(base, 2),
        "limit_high": high, "target": round(target, 2),
        "ramp_minutes": settings.sim_drift_ramp_minutes})
    return Drift(unit=unit, source_column=column, target=target,
                 ramp_minutes=settings.sim_drift_ramp_minutes)


def main(settings: Settings | None = None) -> None:  # pragma: no cover - entrypoint
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = build_database(settings)

    cfg = SimulatorConfig(
        processed_dir=settings.legacy_reports_root / "processed",
        live_dir=settings.live_data_root,
        artifact_root=settings.artifact_root,
        backfill_days=settings.sim_backfill_days,
        drift=build_drift(settings),
        reset=settings.sim_reset,
    )
    sim = LiveSimulator(db, cfg)
    units = sim.seed()
    sim.run_forever(units)


if __name__ == "__main__":  # pragma: no cover
    main()
