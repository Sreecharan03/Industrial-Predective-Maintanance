"""Escalation alert endpoints.

Read paths serve the outbox exactly as recorded (sent/pending/failed/suppressed/
skipped — the UI shows the whole story, including what was deliberately NOT
emailed). The test endpoint sends a REAL email through the same mailer and
report template the dispatcher uses, so "the test passed" means the production
path works, not a lookalike."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from senseminds.alerting import Alert, AlertKind, AlertStatus, SmtpMailer
from senseminds.alerting.report import build_html, build_text
from senseminds.api.deps import AppState, require_roles, state
from senseminds.infrastructure.repositories import UnitOfWork

router = APIRouter(tags=["alerts"])

_ENGINEER = ("maintenance_engineer", "reliability_engineer")


def _row(a: Alert) -> dict:
    return a.model_dump(mode="json")


@router.get("/alerts", dependencies=[Depends(require_roles(*_ENGINEER))])
def recent_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    app: AppState = Depends(state),
) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        return [_row(a) for a in uow.alerts.recent(limit=limit)]


@router.get("/assets/{unit}/alerts", dependencies=[Depends(require_roles(*_ENGINEER))])
def unit_alerts(
    unit: str,
    limit: int = Query(default=100, ge=1, le=500),
    app: AppState = Depends(state),
) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        if uow.assets.get(unit) is None:
            raise HTTPException(status_code=404, detail=f"unknown unit {unit!r}")
        return [_row(a) for a in uow.alerts.recent(limit=limit, unit=unit)]


class TestAlertResponse(BaseModel):
    sent: bool
    to: list[str]
    detail: str


@router.post("/alerts/test", response_model=TestAlertResponse,
             dependencies=[Depends(require_roles("admin"))])
def send_test_alert(app: AppState = Depends(state)) -> TestAlertResponse:
    """Admin-only: send a real email through the production mailer + template."""
    mailer = SmtpMailer(app.settings)
    if not mailer.configured:
        raise HTTPException(status_code=503, detail="SMTP is not configured")
    now = datetime.now(tz=UTC)
    sample = Alert(
        alert_id="test", unit="TEST", identity_key="test", finding_id="test-finding",
        kind=AlertKind.TRIGGERED, severity="critical",
        subject="[SenseMinds 360] TEST — escalation path verification",
        payload={
            "display_name": "Test Machine",
            "finding_type": "threshold_critical",
            "summary": "This is a TEST of the escalation email path.",
            "detail": "Sent from POST /api/v1/alerts/test by an administrator. "
                      "If you can read this, SMTP delivery works end-to-end.",
            "target_key": "test-sensor", "subsystem_key": None,
            "severity": "critical", "confidence": 1.0,
            "detected_at": now.isoformat(),
            "evidence": [{"description": "Requested by admin at",
                          "observed_value": now.strftime("%Y-%m-%d %H:%M:%S UTC")}],
        },
        status=AlertStatus.PENDING, created_at=now,
    )
    try:
        mailer.send(sample.subject,
                    build_text([sample], app.settings.dashboard_url),
                    build_html([sample], app.settings.dashboard_url))
    except Exception as exc:  # surface the real SMTP error to the admin
        raise HTTPException(status_code=502,
                            detail=f"SMTP send failed: {type(exc).__name__}: {exc}") from exc
    return TestAlertResponse(sent=True, to=mailer.recipients,
                             detail="accepted by SMTP server")
