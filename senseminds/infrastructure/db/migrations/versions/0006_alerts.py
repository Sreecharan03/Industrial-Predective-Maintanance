"""alert outbox

Revision ID: 0006_alerts
Revises: 0005_observed_identities
Create Date: 2026-07-14

The escalation outbox. An alert row is written in the SAME transaction as the
finding that caused it, so an alert can never be lost between "detected" and
"emailed" — delivery happens after commit and is retried until it succeeds (or is
marked failed after max attempts). Suppressed and skipped alerts are recorded too,
so the UI shows the full story, not just what happened to reach an inbox.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_alerts"
down_revision: str | None = "0005_observed_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.alert (
            alert_id     TEXT PRIMARY KEY,
            unit         TEXT NOT NULL,
            identity_key TEXT NOT NULL,
            finding_id   TEXT NOT NULL,
            kind         TEXT NOT NULL,   -- triggered | reminder | resolved
            severity     TEXT NOT NULL,
            subject      TEXT NOT NULL,
            payload      JSONB NOT NULL DEFAULT '{}',   -- everything the email needs
            status       TEXT NOT NULL DEFAULT 'pending',
                         -- pending | sent | failed | suppressed | skipped
            attempts     INTEGER NOT NULL DEFAULT 0,
            last_error   TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at      TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_status ON application.alert (status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_identity "
        "ON application.alert (identity_key, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_recent ON application.alert (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS application.alert")
