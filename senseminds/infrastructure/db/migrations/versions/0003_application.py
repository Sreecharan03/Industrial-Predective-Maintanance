"""application aggregates: asset, finding, report, rule_version, model_registry, user

Revision ID: 0003_application
Revises: 0002_knowledge_graph
Create Date: 2026-07-12

ADR-019 D4. One table per aggregate root. Each carries indexed columns for the
queryable/audit dimensions plus a ``document`` JSONB holding the full immutable
domain object (byte-identical reconstruction; repositories stay pure mappers).

Findings are **append-only**, enforced in the database by a trigger that rejects
UPDATE and DELETE - no code path can mutate a recorded finding. New observations
are new rows linked by identity_key / supersedes; re-inserting the same
finding_id is a no-op (handled in the repository via ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_application"
down_revision: str | None = "0002_knowledge_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.asset (
            unit            TEXT PRIMARY KEY,
            equipment_class TEXT NOT NULL,
            display_name    TEXT NOT NULL,
            document        JSONB NOT NULL,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.finding (
            finding_id   TEXT PRIMARY KEY,
            identity_key TEXT NOT NULL,
            unit         TEXT NOT NULL,
            finding_type TEXT NOT NULL,
            category     TEXT NOT NULL,
            origin       TEXT NOT NULL,
            severity     TEXT NOT NULL,
            supersedes   TEXT,
            observed_end TIMESTAMPTZ,
            produced_at  TIMESTAMPTZ NOT NULL,
            document     JSONB NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_finding_unit ON application.finding (unit)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_finding_identity "
        "ON application.finding (identity_key, produced_at)"
    )

    # Append-only: reject any UPDATE/DELETE on a recorded finding, at the DB level.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION application.forbid_finding_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'findings are append-only: % on application.finding is forbidden',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER finding_append_only
        BEFORE UPDATE OR DELETE ON application.finding
        FOR EACH ROW EXECUTE FUNCTION application.forbid_finding_mutation()
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.report (
            report_id    TEXT PRIMARY KEY,
            report_type  TEXT NOT NULL,
            persona      TEXT NOT NULL,
            unit         TEXT NOT NULL,
            status       TEXT NOT NULL,
            requested_at TIMESTAMPTZ NOT NULL,
            document     JSONB NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_report_unit ON application.report (unit)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.rule_version (
            rule_id    TEXT NOT NULL,
            version    TEXT NOT NULL,
            enabled    BOOLEAN NOT NULL,
            document   JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (rule_id, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.model_registry (
            model_id               TEXT NOT NULL,
            version                TEXT NOT NULL,
            trained_at             TIMESTAMPTZ NOT NULL,
            feature_schema_version TEXT NOT NULL,
            seed                   INTEGER NOT NULL,
            metadata               JSONB NOT NULL,
            artifact               JSONB NOT NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (model_id, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.role (
            name        TEXT PRIMARY KEY,
            description TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS application.app_user (
            username        TEXT PRIMARY KEY,
            email           TEXT NOT NULL DEFAULT '',
            hashed_password TEXT NOT NULL DEFAULT '',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            roles           JSONB NOT NULL DEFAULT '[]',
            document        JSONB NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS application.app_user")
    op.execute("DROP TABLE IF EXISTS application.role")
    op.execute("DROP TABLE IF EXISTS application.model_registry")
    op.execute("DROP TABLE IF EXISTS application.rule_version")
    op.execute("DROP TABLE IF EXISTS application.report")
    op.execute("DROP TRIGGER IF EXISTS finding_append_only ON application.finding")
    op.execute("DROP FUNCTION IF EXISTS application.forbid_finding_mutation()")
    op.execute("DROP TABLE IF EXISTS application.finding")
    op.execute("DROP TABLE IF EXISTS application.asset")
