"""SQLAlchemy engine + per-store session factory (ADR-019 D0, R4).

`Database` holds one engine per logical store. Today all three resolve to the
same URL (one local Postgres); each is independently addressable so a future
split is a config change. `session(schema)` is a transactional unit of work:
commit on success, rollback on error — the transaction boundary of ADR-019 §7.
A unit of work never spans two schemas (R4).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from senseminds.config import Settings
from senseminds.infrastructure.db.schema import (
    APPLICATION,
    KNOWLEDGE,
    SENSOR_HISTORY,
    StoreSchema,
)


class Database:
    """Owns a SQLAlchemy engine + session factory per logical store."""

    def __init__(self, urls: dict[StoreSchema, str], *, pool_recycle_seconds: int = 1800,
                 pool_size: int = 5, max_overflow: int = 10) -> None:
        # Resilience is SQLAlchemy's own, not custom retry logic (deployment
        # refinement): pool_pre_ping issues a lightweight liveness check and
        # transparently replaces a connection the database dropped (e.g. after a
        # DB restart), so callers never see a stale-connection error. pool_recycle
        # proactively retires connections before a server/idle timeout can. These
        # cover transient connection loss; anything beyond that is a real fault
        # and should surface, not be silently retried.
        self._engines: dict[StoreSchema, Engine] = {
            schema: create_engine(
                url, future=True,
                pool_pre_ping=True,
                pool_recycle=pool_recycle_seconds,
                pool_size=pool_size,
                max_overflow=max_overflow,
            )
            for schema, url in urls.items()
        }
        self._factories: dict[StoreSchema, sessionmaker[Session]] = {
            schema: sessionmaker(bind=engine, future=True, expire_on_commit=False)
            for schema, engine in self._engines.items()
        }

    def engine(self, schema: StoreSchema) -> Engine:
        return self._engines[schema]

    def session_factory(self, schema: StoreSchema) -> sessionmaker[Session]:
        return self._factories[schema]

    @contextmanager
    def session(self, schema: StoreSchema) -> Iterator[Session]:
        """A transactional unit of work for one store (commit/rollback/close)."""
        session = self._factories[schema]()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        for engine in self._engines.values():
            engine.dispose()


def build_database(settings: Settings) -> Database:
    """Construct a `Database` from settings, per-store URL falling back to base."""
    base = settings.database_url
    urls: dict[StoreSchema, str] = {
        SENSOR_HISTORY: settings.sensor_history_url or base,
        KNOWLEDGE: settings.knowledge_url or base,
        APPLICATION: settings.application_url or base,
    }
    return Database(
        urls,
        pool_recycle_seconds=settings.db_pool_recycle_seconds,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
