"""Alert model — one escalation event in a condition's lifecycle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from senseminds.domain.base import FrozenModel


class AlertKind(StrEnum):
    TRIGGERED = "triggered"   # a condition became critical
    REMINDER = "reminder"     # it is STILL critical and nobody has dealt with it
    RESOLVED = "resolved"     # it cleared


class AlertStatus(StrEnum):
    PENDING = "pending"       # committed with the finding; email not yet attempted
    SENT = "sent"
    FAILED = "failed"         # gave up after max attempts (visible, never silent)
    SUPPRESSED = "suppressed" # cooldown (flapping) — recorded, deliberately not emailed
    SKIPPED = "skipped"       # SMTP not configured — recorded, nothing to send with


class Alert(FrozenModel):
    alert_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    identity_key: str = Field(min_length=1)
    finding_id: str = Field(min_length=1)
    kind: AlertKind
    severity: str
    subject: str
    payload: dict[str, object] = Field(default_factory=dict)
    status: AlertStatus = AlertStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime
    sent_at: datetime | None = None
