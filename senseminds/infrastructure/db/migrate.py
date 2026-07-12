"""Alembic migration runner (ADR-019 D1).

Programmatic entrypoint so migrations run identically from the CLI
(``python -m senseminds.infrastructure.db.migrate``), the Docker ``migrate``
one-shot service, and tests. Config is built in-code (no static alembic.ini) so
the DB URL always comes from validated `Settings`.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from senseminds.config import get_settings

_MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str | None = None) -> Config:
    """Build an Alembic Config pointed at our migrations + the settings URL."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url or get_settings().database_url)
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)


if __name__ == "__main__":  # pragma: no cover - container/CLI entrypoint
    upgrade()
