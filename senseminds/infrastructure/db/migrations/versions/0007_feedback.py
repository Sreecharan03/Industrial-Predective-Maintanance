"""engineer feedback on learned findings

Revision ID: 0007_feedback
Revises: 0006_alerts
Create Date: 2026-07-18

The label store (ADR-016 R2, ADR-007 label-bootstrap loop). An engineer's verdict
on a LEARNED hypothesis is what eventually becomes a supervised training label, so
this table is treated as primary data, not derived state:

* Keyed on **identity_key**, not finding_id. A finding_id changes with every new
  observation of the same condition; identity_key does not. A verdict is about the
  condition ("this novelty is a false positive"), so it must survive the next
  observation - and it must still be there after the condition clears, because a
  cleared condition that was once labelled is exactly the training example we want.
* **Append-only.** A changed verdict is a new row, never an overwrite, so the
  label history (and any disagreement between engineers) stays auditable. Reads
  take the latest row per identity.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_feedback"
down_revision: str | None = "0006_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.feedback (
            feedback_id  TEXT PRIMARY KEY,
            identity_key TEXT NOT NULL,   -- the condition (stable across observations)
            finding_id   TEXT NOT NULL,   -- the exact observation reviewed (audit)
            unit         TEXT NOT NULL,
            verdict      TEXT NOT NULL,   -- confirmed_novelty | expected_behaviour
                                          -- | false_positive
            author       TEXT NOT NULL,   -- taken from the token, never the request body
            note         TEXT NOT NULL DEFAULT '',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feedback_identity "
        "ON application.feedback (identity_key, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feedback_unit "
        "ON application.feedback (unit, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feedback_recent "
        "ON application.feedback (created_at DESC)"
    )

    # Same guarantee the findings table has: a label may be superseded, never
    # rewritten or deleted, or the training set silently changes under us.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION application.feedback_is_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'application.feedback is append-only (attempted %)', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_feedback_append_only ON application.feedback")
    op.execute(
        """
        CREATE TRIGGER trg_feedback_append_only
        BEFORE UPDATE OR DELETE ON application.feedback
        FOR EACH ROW EXECUTE FUNCTION application.feedback_is_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_feedback_append_only ON application.feedback")
    op.execute("DROP FUNCTION IF EXISTS application.feedback_is_append_only()")
    op.execute("DROP TABLE IF EXISTS application.feedback")
