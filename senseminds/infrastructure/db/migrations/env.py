"""Alembic environment (online migrations only).

We manage raw DDL (schemas, TimescaleDB hypertables) by hand rather than
autogenerating from ORM metadata, so no ``target_metadata`` is needed.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool, future=True
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


run_migrations_online()
