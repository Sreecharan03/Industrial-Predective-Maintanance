"""Engineer feedback on learned findings — the label-bootstrap loop (ADR-016 R2).

An engineer's verdict on a hypothesis is the platform's only source of supervised
labels, so this endpoint is deliberately strict about three things:

1. **The author comes from the token**, never the request body — a label whose
   author could be spoofed is worthless as an audit record.
2. **Only LEARNED findings can be judged.** A deterministic finding is a
   measurement, not a hypothesis; "false positive" is not a meaningful verdict on
   a reading that did cross a setpoint. If a threshold looks wrong, the platform
   already raises `threshold_misspecified` for that.
3. **Verdicts key on identity_key**, so a label survives the next observation of
   the same condition and remains valid after the condition clears.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from senseminds.api.deps import AppState, Principal, require_roles, state
from senseminds.findings import FindingOrigin
from senseminds.infrastructure.repositories import UnitOfWork
from senseminds.knowledge_graph import FeedbackProjector
from senseminds.pattern_learning.feedback import FeedbackVerdict, HumanFeedback

router = APIRouter(tags=["feedback"])

_ENGINEER = ("maintenance_engineer", "reliability_engineer")
# Module-level singleton: calling require_roles() inline in a default would
# rebuild the dependency on every request (and ruff B008 rightly objects).
_ENGINEER_DEP = require_roles(*_ENGINEER)

# Roughly where a supervised model becomes trainable (docs/ML strategy §6).
_LABEL_TARGET = 200


class FeedbackRequest(BaseModel):
    verdict: FeedbackVerdict
    note: str = Field(default="", max_length=2000)


class FeedbackOut(BaseModel):
    feedback_id: str
    identity_key: str
    finding_id: str
    unit: str
    verdict: FeedbackVerdict
    author: str
    note: str
    created_at: datetime


def _out(f: HumanFeedback) -> FeedbackOut:
    return FeedbackOut(
        feedback_id=f.feedback_id, identity_key=f.finding_identity_key,
        finding_id=f.finding_id, unit=f.unit, verdict=f.verdict,
        author=f.author, note=f.note, created_at=f.created_at,
    )


@router.post("/findings/{identity_key}/feedback", response_model=FeedbackOut, status_code=201)
def record_feedback(
    identity_key: str,
    req: FeedbackRequest,
    principal: Principal = Depends(_ENGINEER_DEP),
    app: AppState = Depends(state),
) -> FeedbackOut:
    """Record an engineer's verdict on a learned hypothesis."""
    with UnitOfWork(app.db) as uow:
        finding = uow.findings.latest(identity_key)
        if finding is None:
            raise HTTPException(status_code=404, detail=f"unknown finding {identity_key!r}")
        if finding.origin is not FindingOrigin.LEARNED:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"finding is {finding.origin.value}, not a learned hypothesis. "
                    "Deterministic findings are measurements, not predictions to confirm."
                ),
            )

        feedback = HumanFeedback(
            feedback_id=uuid.uuid4().hex,
            finding_identity_key=identity_key,
            finding_id=finding.finding_id,
            unit=finding.equipment_key,
            verdict=req.verdict,
            author=principal.username,     # from the token, not the body
            note=req.note,
            created_at=datetime.now(tz=UTC),
        )
        uow.feedback.record(feedback)

        # Close the loop: the verdict becomes part of the graph's knowledge.
        FeedbackProjector(uow.graph).project(feedback)

        # Return what is now current for this condition (a repeated identical
        # verdict is a no-op, so echo the stored row rather than the request).
        stored = uow.feedback.latest_for(identity_key, principal.username)
    return _out(stored or feedback)


@router.get("/findings/{identity_key}/feedback", response_model=list[FeedbackOut],
            dependencies=[Depends(require_roles(*_ENGINEER))])
def feedback_history(identity_key: str, app: AppState = Depends(state)) -> list[FeedbackOut]:
    """Full verdict history for one condition, oldest first (incl. disagreements)."""
    with UnitOfWork(app.db) as uow:
        return [_out(f) for f in uow.feedback.for_finding(identity_key)]


@router.get("/feedback", response_model=list[FeedbackOut],
            dependencies=[Depends(require_roles(*_ENGINEER))])
def recent_feedback(
    limit: int = Query(default=100, ge=1, le=500),
    app: AppState = Depends(state),
) -> list[FeedbackOut]:
    with UnitOfWork(app.db) as uow:
        return [_out(f) for f in uow.feedback.recent(limit=limit)]


@router.get("/assets/{unit}/feedback", response_model=list[FeedbackOut],
            dependencies=[Depends(require_roles(*_ENGINEER))])
def unit_feedback(
    unit: str,
    limit: int = Query(default=100, ge=1, le=500),
    app: AppState = Depends(state),
) -> list[FeedbackOut]:
    with UnitOfWork(app.db) as uow:
        if uow.assets.get(unit) is None:
            raise HTTPException(status_code=404, detail=f"unknown unit {unit!r}")
        return [_out(f) for f in uow.feedback.recent(limit=limit, unit=unit)]


class LabelProgress(BaseModel):
    labelled_conditions: int
    total_verdicts: int
    contributors: int
    units_covered: int
    by_verdict: dict[str, int]
    target: int
    percent_to_target: float
    phase_c_ready: bool


@router.get("/feedback/stats", response_model=LabelProgress,
            dependencies=[Depends(require_roles(*_ENGINEER))])
def label_progress(app: AppState = Depends(state)) -> LabelProgress:
    """How close the platform is to having a trainable supervised dataset."""
    with UnitOfWork(app.db) as uow:
        s = uow.feedback.stats()
    labelled = int(s["labelled_conditions"])  # type: ignore[arg-type]
    return LabelProgress(
        labelled_conditions=labelled,
        total_verdicts=int(s["total_verdicts"]),      # type: ignore[arg-type]
        contributors=int(s["contributors"]),          # type: ignore[arg-type]
        units_covered=int(s["units_covered"]),        # type: ignore[arg-type]
        by_verdict=s["by_verdict"],                   # type: ignore[arg-type]
        target=_LABEL_TARGET,
        percent_to_target=round(min(labelled / _LABEL_TARGET * 100, 100.0), 1),
        phase_c_ready=labelled >= _LABEL_TARGET,
    )
