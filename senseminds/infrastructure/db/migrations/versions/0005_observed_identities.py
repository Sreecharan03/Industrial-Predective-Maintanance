"""engine_run.observed_identities + TimescaleDB compression

Revision ID: 0005_observed_identities
Revises: 0004_engine_run
Create Date: 2026-07-13

Two fixes for problems that only appear once data actually flows.

1. We stop re-recording findings that have not changed (see
   `application/finding_delta.py`). That alone would make a *cleared* condition
   look permanent, because "current" is the latest observation per identity and a
   condition that stops being produced would keep its last row forever. So each run
   now records the set of conditions it OBSERVED, and "current" is filtered to the
   latest run's set — a condition that clears simply drops out.

2. The sensor hypertable had no compression policy (ADR-019 designed one, it was
   never applied). At a 30-second cadence, raw data grows without bound.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_observed_identities"
down_revision: str | None = "0004_engine_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE application.engine_run "
        "ADD COLUMN IF NOT EXISTS observed_identities JSONB NOT NULL DEFAULT '[]'"
    )
    # Phase-B models (novelty / regimes / forecasting) are about slow trends and are
    # far too expensive to run every 30s. This marks the runs that did, so the use
    # case can throttle them to their own cadence.
    op.execute(
        "ALTER TABLE application.engine_run "
        "ADD COLUMN IF NOT EXISTS learned BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # Compress chunks older than 7 days, grouped the way we query them.
    op.execute(
        """
        ALTER TABLE sensor_history.sensor_reading SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'unit, sensor_key',
            timescaledb.compress_orderby = 'time DESC'
        )
        """
    )
    op.execute(
        """
        SELECT add_compression_policy('sensor_history.sensor_reading',
                                      INTERVAL '7 days', if_not_exists => TRUE)
        """
    )


def downgrade() -> None:
    op.execute(
        "SELECT remove_compression_policy('sensor_history.sensor_reading', "
        "if_exists => TRUE)"
    )
    op.execute("ALTER TABLE sensor_history.sensor_reading SET (timescaledb.compress = false)")
    op.execute("ALTER TABLE application.engine_run DROP COLUMN IF EXISTS learned")
    op.execute("ALTER TABLE application.engine_run DROP COLUMN IF EXISTS observed_identities")
