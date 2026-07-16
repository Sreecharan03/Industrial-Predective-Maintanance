"""SMTP delivery. Deliberately dumb: connect, STARTTLS, authenticate, send,
raise on any failure — retry/backoff/bookkeeping live in the dispatcher."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from senseminds.config.settings import Settings


class SmtpMailer:
    """Thin smtplib wrapper. `send` raises on failure; the caller records it."""

    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._starttls = settings.smtp_starttls
        self._from = settings.mail_from or settings.smtp_user
        self._to = [a.strip() for a in settings.mail_to.split(",") if a.strip()]

    @property
    def configured(self) -> bool:
        return bool(self._host and self._from and self._to)

    @property
    def recipients(self) -> list[str]:
        return list(self._to)

    def send(self, subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = ", ".join(self._to)
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
            if self._starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)
