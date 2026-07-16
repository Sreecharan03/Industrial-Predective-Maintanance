"""Alert escalation (outbox pattern).

Policy decides WHEN (transition-based incidents), the report decides WHAT
(grounded, plain-English email), the mailer is dumb SMTP, and the dispatcher
delivers post-commit with retries. Alert rows commit with the findings that
caused them, so detection and notification can never diverge silently."""

from senseminds.alerting.dispatcher import AlertDispatcher
from senseminds.alerting.factory import build_alerting
from senseminds.alerting.mailer import SmtpMailer
from senseminds.alerting.models import Alert, AlertKind, AlertStatus
from senseminds.alerting.policy import AlertPolicy

__all__ = [
    "Alert",
    "AlertDispatcher",
    "AlertKind",
    "AlertPolicy",
    "AlertStatus",
    "SmtpMailer",
    "build_alerting",
]
