"""One place every process (API, worker, simulator) wires alerting the same way."""

from __future__ import annotations

from datetime import timedelta

from senseminds.alerting.dispatcher import AlertDispatcher
from senseminds.alerting.mailer import SmtpMailer
from senseminds.alerting.policy import AlertPolicy
from senseminds.config.settings import Settings
from senseminds.infrastructure.db import Database


def build_alerting(db: Database, settings: Settings) -> tuple[AlertPolicy, AlertDispatcher]:
    policy = AlertPolicy(
        reminder=timedelta(minutes=settings.alert_reminder_minutes),
        cooldown=timedelta(minutes=settings.alert_cooldown_minutes),
    )
    dispatcher = AlertDispatcher(db, SmtpMailer(settings), settings.dashboard_url)
    return policy, dispatcher
