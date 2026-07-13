"""Reading ingest endpoint — the production path for real machines.

Any edge gateway, historian export, OPC-UA/MQTT bridge or script can POST readings
here. They go through the SAME validation and sink a CSV bootstrap uses, so nothing
downstream knows or cares where the data came from.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from senseminds.api.deps import AppState, require_roles, state
from senseminds.ingestion import DbReadingSink, Reading, ReadingValidation

router = APIRouter(tags=["ingest"])

_INGEST = ("maintenance_engineer", "reliability_engineer")


class ReadingIn(BaseModel):
    sensor_key: str = Field(min_length=1)
    time: datetime
    value: float | None = None
    quality: int = 0


class IngestRequest(BaseModel):
    unit: str = Field(min_length=1)
    readings: list[ReadingIn] = Field(min_length=1)
    source: str = "api"
    analyze: bool = Field(
        default=False,
        description="Re-run the analysis immediately (otherwise the worker picks it up).",
    )


class IngestResponse(BaseModel):
    unit: str
    accepted: int
    rejected: int
    reasons: list[str] = []
    analysed: bool = False
    finding_count: int | None = None


@router.post("/readings", response_model=IngestResponse,
             dependencies=[Depends(require_roles(*_INGEST))])
def ingest(req: IngestRequest, app: AppState = Depends(state)) -> IngestResponse:
    readings = [
        Reading(unit=req.unit, sensor_key=r.sensor_key, time=r.time,
                value=r.value, quality=r.quality, source=req.source)
        for r in req.readings
    ]
    outcome = ReadingValidation(req.unit).validate(readings)
    written = DbReadingSink(app.db).write(outcome.accepted)

    result = None
    if req.analyze and written:
        result = app.analysis.run(req.unit)

    return IngestResponse(
        unit=req.unit,
        accepted=written,
        rejected=len(outcome.rejected),
        reasons=sorted({r.reason for r in outcome.rejected})[:5],
        analysed=result is not None,
        finding_count=result.finding_count if result else None,
    )
