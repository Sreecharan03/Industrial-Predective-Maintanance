"""Sensor telemetry (ADR-018 §2 — the explicit-request path).

The knowledge graph and the LLM are deliberately telemetry-free: raw sensor
streams are never retrieved for *reasoning*. They ARE served here, explicitly,
as **presentation data** for charts — read-only, downsampled with TimescaleDB's
time_bucket so a long window stays cheap.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from senseminds.api.deps import AppState, current_user, state
from senseminds.catalog import build_asset, thresholds_for
from senseminds.domain.enums import ThresholdStatus
from senseminds.infrastructure.db import SENSOR_HISTORY
from senseminds.infrastructure.repositories import UnitOfWork

router = APIRouter(prefix="/assets", tags=["telemetry"],
                   dependencies=[Depends(current_user)])

_SERIES = text(
    """
    SELECT sensor_key,
           time_bucket(make_interval(secs => :bucket), time) AS t,
           avg(value) AS v
    FROM sensor_history.sensor_reading
    WHERE unit = :unit
      AND time > now() - make_interval(secs => :window)
      AND value IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 1, 2
    """
)
_LATEST = text(
    """
    SELECT DISTINCT ON (sensor_key) sensor_key, time, value
    FROM sensor_history.sensor_reading
    WHERE unit = :unit AND value IS NOT NULL
    ORDER BY sensor_key, time DESC
    """
)


@router.get("/{unit}/telemetry")
def telemetry(
    unit: str,
    hours: float = Query(default=6, gt=0, le=720, description="Window to chart."),
    points: int = Query(default=90, ge=10, le=500, description="Buckets per sensor."),
    app: AppState = Depends(state),
) -> dict:
    """Latest value + a downsampled trend for every sensor on the asset."""
    window = hours * 3600
    bucket = max(30.0, window / points)  # never finer than the 30s cadence

    with app.db.session(SENSOR_HISTORY) as session:
        rows = session.execute(
            _SERIES, {"unit": unit, "bucket": bucket, "window": window}
        ).all()
        latest = {
            r[0]: {"time": r[1].isoformat(), "value": round(float(r[2]), 2)}
            for r in session.execute(_LATEST, {"unit": unit})
        }

    if not latest:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no telemetry for {unit!r}")

    series: dict[str, list[dict]] = {}
    for key, t, v in rows:
        series.setdefault(key, []).append(
            {"t": t.isoformat(), "v": round(float(v), 2)}
        )

    with UnitOfWork(app.db) as uow:
        asset = uow.assets.get(unit)
    if asset is None:
        asset = build_asset(unit, [])
    bands = thresholds_for(unit, asset)

    sensors = []
    for sensor in asset.sensors:
        band = bands.get(sensor.key)
        available = band is not None and band.status is ThresholdStatus.AVAILABLE
        sensors.append({
            "key": sensor.key,
            "display_name": sensor.display_name,
            "unit_symbol": sensor.unit.symbol,
            "latest": latest.get(sensor.key),
            "threshold": ({"low": band.minimum, "high": band.maximum} if available else None),
            "points": series.get(sensor.key, []),
        })

    return {"unit": unit, "hours": hours, "sensors": sensors}
