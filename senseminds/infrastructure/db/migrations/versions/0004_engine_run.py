"""engine_run: analysis-run audit record (ADR-019 D5, R2)

Revision ID: 0004_engine_run
Revises: 0003_application
Create Date: 2026-07-12

One row per analysis run of the AnalysisUseCase, in the **application** schema
(execution metadata, not sensor history - R2). Linked to the input hash and the
artifacts it produced, for complete auditability. UNIQUE(unit, input_hash) is the
idempotency key: the same input can only ever record one completed run.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_engine_run"
down_revision: str | None = "0003_application"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.engine_run (
            run_id          TEXT PRIMARY KEY,
            unit            TEXT NOT NULL,
            input_hash      TEXT NOT NULL,
            status          TEXT NOT NULL,
            started_at      TIMESTAMPTZ NOT NULL,
            finished_at     TIMESTAMPTZ,
            finding_count   INTEGER NOT NULL DEFAULT 0,
            engine_versions JSONB NOT NULL DEFAULT '{}',
            artifact_ids    JSONB NOT NULL DEFAULT '[]',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (unit, input_hash)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_engine_run_unit ON application.engine_run (unit)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS application.engine_run")
