"""baseline: extensions, three schemas, sensor_history hypertable

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-12

ADR-019 D1. Creates the TimescaleDB extension, the three independent logical
schemas (sensor_history / knowledge / application — no cross-schema FKs, R4),
and the sensor_history operational tables. Application/knowledge tables arrive
with their own adapters in later steps; the schemas exist now so boundaries are
established. Compression / continuous aggregates are deferred to D8 (performance
never precedes parity).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    for schema in ("sensor_history", "knowledge", "application"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    # --- sensor_history: operational time-series (TimescaleDB hypertable) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_history.sensor_reading (
            time       TIMESTAMPTZ      NOT NULL,
            unit       TEXT             NOT NULL,
            sensor_key TEXT             NOT NULL,
            value      DOUBLE PRECISION,
            quality    SMALLINT         NOT NULL DEFAULT 0,
            source     TEXT             NOT NULL DEFAULT 'csv_bootstrap',
            PRIMARY KEY (unit, sensor_key, time)
        )
        """
    )
    op.execute(
        """
        SELECT create_hypertable('sensor_history.sensor_reading', 'time',
            chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_reading_unit_sensor_time
            ON sensor_history.sensor_reading (unit, sensor_key, time DESC)
        """
    )

    # per-unit ingestion watermark (last persisted reading time)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_history.ingest_watermark (
            unit      TEXT        PRIMARY KEY,
            last_time TIMESTAMPTZ NOT NULL
        )
        """
    )

    # Per-unit sensor identity: the exact source column each key came from, in
    # order. The processed CSVs use stripped headers ("Oil Pressure") while the
    # catalog's canonical column carries the unit ("Oil Pressure (kg/cm2)"), and
    # thresholds are matched by source column - so this mapping must be persisted,
    # not re-derived, for the reconstructed Asset (and thus every engine output)
    # to be byte-identical.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_history.unit_sensor (
            unit          TEXT     NOT NULL,
            sensor_key    TEXT     NOT NULL,
            source_column TEXT     NOT NULL,
            ordinal       SMALLINT NOT NULL,
            PRIMARY KEY (unit, sensor_key)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sensor_history.unit_sensor")
    op.execute("DROP TABLE IF EXISTS sensor_history.ingest_watermark")
    op.execute("DROP TABLE IF EXISTS sensor_history.sensor_reading")
    # schemas/extension left intact on downgrade (shared, cheap to keep).
