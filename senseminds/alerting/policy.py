"""Escalation policy — WHEN to alert.

Alerts are transition-based, not row-based: one incident produces one clear
story — *triggered* when a condition becomes critical, *reminder* while it stays
critical unattended, *resolved* when it clears — instead of an email per
30-second tick. The edge cases handled here, explicitly:

1. **New critical** (was not critical, now is)         -> TRIGGERED
2. **Cleared** (was critical, now isn't — either the severity dropped or the
   condition disappeared from the latest run entirely) -> RESOLVED
3. **Still critical past the reminder interval**       -> REMINDER (repeats)
4. **Flapping** (a value hovering at its limit that re-triggers within the
   cooldown of its own resolution) -> the alert is still RECORDED but marked
   SUPPRESSED, so the UI shows the flapping without an inbox full of noise.
5. **Resolution of something never announced** (triggered before the alerting
   system existed, or its trigger was itself suppressed) -> resolved silently /
   suppressed to match — we never email "resolved" for an alarm nobody received.
6. **Critical that predates alerting** (already critical, no alert row ever)
   -> treated as newly TRIGGERED so it is announced exactly once.
7. **Wording/value changes while critical** do NOT re-trigger — the identity is
   unchanged, so the reminder cycle carries it.
8. Delivery concerns (SMTP down/unconfigured) are *not* decided here — the
   policy always records the truth; the dispatcher handles sending.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from senseminds.alerting.models import Alert, AlertKind, AlertStatus
from senseminds.domain.enums import Severity
from senseminds.findings import Finding


def _payload(finding: Finding, display_name: str) -> dict[str, object]:
    """Everything the email report needs, frozen at decision time."""
    return {
        "display_name": display_name,
        "finding_type": finding.finding_type.value,
        "summary": finding.summary,
        "detail": finding.detail,
        "target_key": finding.target_key,
        "subsystem_key": finding.subsystem_key,
        "severity": finding.severity.value,
        "confidence": float(finding.confidence.value),
        "detected_at": finding.provenance.produced_at.isoformat(),
        "evidence": [
            {"description": e.description, "observed_value": e.observed_value}
            for e in finding.evidence
        ],
    }


class AlertPolicy:
    """Decide the alerts one analysis run implies. Pure — no I/O."""

    def __init__(self, reminder: timedelta, cooldown: timedelta) -> None:
        self._reminder = reminder
        self._cooldown = cooldown

    def decide(
        self,
        unit: str,
        display_name: str,
        previous: tuple[Finding, ...],
        observed: tuple[Finding, ...],
        latest: dict[str, Alert],
        now: datetime,
    ) -> list[Alert]:
        """`previous` = the current view BEFORE this run; `observed` = this run's
        full finding set; `latest` = newest alert per identity for this unit."""
        prev_crit = {f.identity_key: f for f in previous if f.severity is Severity.CRITICAL}
        now_crit = {f.identity_key: f for f in observed if f.severity is Severity.CRITICAL}
        alerts: list[Alert] = []

        for key, finding in sorted(now_crit.items()):
            last = latest.get(key)
            if key not in prev_crit:
                # Edge 4: re-triggering within the cooldown of its own resolution
                # is flapping — record it, don't email it.
                flapping = (
                    last is not None
                    and last.kind is AlertKind.RESOLVED
                    and (now - last.created_at) < self._cooldown
                )
                alerts.append(self._make(
                    unit, display_name, finding, AlertKind.TRIGGERED, now,
                    AlertStatus.SUPPRESSED if flapping else AlertStatus.PENDING,
                ))
            elif last is None:
                # Edge 6: critical since before alerting existed — announce once.
                alerts.append(self._make(
                    unit, display_name, finding, AlertKind.TRIGGERED, now,
                    AlertStatus.PENDING,
                ))
            elif (
                last.kind in (AlertKind.TRIGGERED, AlertKind.REMINDER)
                and (now - last.created_at) >= self._reminder
            ):
                # Edge 3: still critical, nobody has dealt with it — escalate again.
                alerts.append(self._make(
                    unit, display_name, finding, AlertKind.REMINDER, now,
                    AlertStatus.PENDING,
                ))

        for key, finding in sorted(prev_crit.items()):
            if key in now_crit:
                continue
            last = latest.get(key)
            if last is None or last.kind is AlertKind.RESOLVED:
                # Edge 5: nothing was ever announced (or it's already resolved) —
                # there is no open incident to close.
                continue
            # If the trigger itself was suppressed (flapping), suppress the
            # resolution too — the inbox never heard about this incident.
            status = (
                AlertStatus.SUPPRESSED
                if last.status is AlertStatus.SUPPRESSED
                else AlertStatus.PENDING
            )
            alerts.append(self._make(
                unit, display_name, finding, AlertKind.RESOLVED, now, status
            ))

        return alerts

    @staticmethod
    def _make(
        unit: str,
        display_name: str,
        finding: Finding,
        kind: AlertKind,
        now: datetime,
        status: AlertStatus,
    ) -> Alert:
        headline = {
            AlertKind.TRIGGERED: "CRITICAL",
            AlertKind.REMINDER: "STILL CRITICAL",
            AlertKind.RESOLVED: "RESOLVED",
        }[kind]
        return Alert(
            alert_id=uuid.uuid4().hex,
            unit=unit,
            identity_key=finding.identity_key,
            finding_id=finding.finding_id,
            kind=kind,
            severity=finding.severity.value,
            subject=f"[SenseMinds 360] {headline} — {display_name or unit}: {finding.summary}",
            payload=_payload(finding, display_name),
            status=status,
            created_at=now,
        )
