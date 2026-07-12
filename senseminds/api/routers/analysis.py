"""Analysis trigger + engine-run audit endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from senseminds.api.deps import AppState, require_roles, state
from senseminds.infrastructure.repositories import UnitOfWork

router = APIRouter(tags=["analysis"])

_ENGINEER = ("maintenance_engineer", "reliability_engineer")


class AnalyzeRequest(BaseModel):
    unit: str


class AnalyzeResponse(BaseModel):
    unit: str
    run_id: str | None
    input_hash: str
    finding_count: int
    replayed: bool


@router.post("/analyze", response_model=AnalyzeResponse,
             dependencies=[Depends(require_roles(*_ENGINEER))])
def analyze(req: AnalyzeRequest, app: AppState = Depends(state)) -> AnalyzeResponse:
    result = app.analysis.run(req.unit)
    return AnalyzeResponse(
        unit=result.unit, run_id=result.run_id, input_hash=result.input_hash,
        finding_count=result.finding_count, replayed=result.replayed,
    )


@router.get("/runs/{unit}", dependencies=[Depends(require_roles(*_ENGINEER))])
def runs(unit: str, app: AppState = Depends(state)) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        history = uow.runs.for_unit(unit)
    return [r.model_dump(mode="json") for r in history]
