"""Post-commit alert delivery (the outbox consumer).

The policy writes alert rows in the SAME transaction as the findings, so an
alert can never be lost between "detected" and "emailed". This dispatcher runs
AFTER that transaction commits: it picks up every pending row (including ones a
previous cycle failed to send), groups them into one email per (unit, kind),
and records the outcome. Because the analysis loop runs every 30 seconds,
failed sends are retried naturally on the next tick — no extra scheduler.

Nothing here can fail an analysis run: the caller wraps dispatch() in
try/except, and this module never raises past its own bookkeeping."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import groupby

from senseminds.alerting.mailer import SmtpMailer
from senseminds.alerting.models import Alert, AlertStatus
from senseminds.alerting.report import build_html, build_text, subject_for
from senseminds.infrastructure.db import Database
from senseminds.infrastructure.logging import get_logger

_log = get_logger(__name__)

MAX_ATTEMPTS = 5


class AlertDispatcher:
    """Deliver pending outbox rows; every outcome is recorded, none is silent."""

    def __init__(self, db: Database, mailer: SmtpMailer, dashboard_url: str) -> None:
        self._db = db
        self._mailer = mailer
        self._dashboard_url = dashboard_url

    def dispatch(self) -> dict[str, int]:
        """Send everything sendable. Returns counts for logging/endpoints."""
        # Imported here, not at module level: the repositories module itself
        # imports alerting.models, so a top-level import would be circular.
        from senseminds.infrastructure.repositories.unit_of_work import UnitOfWork

        counts = {"sent": 0, "skipped": 0, "failed": 0, "retry": 0}
        with UnitOfWork(self._db) as uow:
            pending = uow.alerts.pending(max_attempts=MAX_ATTEMPTS)
            if not pending:
                return counts

            if not self._mailer.configured:
                # Recorded, visible in the UI as 'skipped' — never a blind drop.
                for alert in pending:
                    uow.alerts.mark(alert.alert_id, AlertStatus.SKIPPED,
                                    attempts=alert.attempts,
                                    last_error="SMTP not configured")
                counts["skipped"] = len(pending)
                _log.warning("alerts_skipped_no_smtp", extra={"count": len(pending)})
                return counts

            # One email per (unit, kind): a cascade of criticals on the same
            # machine reads as one report, not an inbox flood.
            def keyfn(a: Alert) -> tuple[str, str]:
                return (a.unit, a.kind.value)

            for (unit, kind), group_iter in groupby(sorted(pending, key=keyfn), key=keyfn):
                group: list[Alert] = list(group_iter)
                try:
                    self._mailer.send(
                        subject_for(group),
                        build_text(group, self._dashboard_url),
                        build_html(group, self._dashboard_url),
                    )
                except Exception as exc:  # noqa: BLE001 — outcome IS the record
                    error = f"{type(exc).__name__}: {exc}"
                    for alert in group:
                        attempts = alert.attempts + 1
                        final = attempts >= MAX_ATTEMPTS
                        uow.alerts.mark(
                            alert.alert_id,
                            AlertStatus.FAILED if final else AlertStatus.PENDING,
                            attempts=attempts, last_error=error[:500],
                        )
                        counts["failed" if final else "retry"] += 1
                    _log.error("alert_send_failed",
                               extra={"unit": unit, "kind": kind, "error": error})
                else:
                    now = datetime.now(tz=UTC)
                    for alert in group:
                        uow.alerts.mark(alert.alert_id, AlertStatus.SENT,
                                        attempts=alert.attempts + 1, sent_at=now)
                    counts["sent"] += len(group)
                    _log.info("alert_sent", extra={
                        "unit": unit, "kind": kind, "conditions": len(group),
                        "to": ",".join(self._mailer.recipients)})
        return counts
