"""Unit of work (ADR-019 D4, §7).

One transaction, one session, all application repositories bound to it. A use-case
opens a `UnitOfWork`, writes through several repositories, and either the whole
block commits or - on any exception - the whole block rolls back, leaving the
database consistent. This is the transaction boundary the aggregate repositories
deliberately do not own themselves.
"""

from __future__ import annotations

from types import TracebackType

from senseminds.infrastructure.db import APPLICATION, Database
from senseminds.infrastructure.repositories.postgres import (
    PostgresAssetRepository,
    PostgresEngineRunRepository,
    PostgresFindingRepository,
    PostgresModelRegistry,
    PostgresReportRepository,
    PostgresRuleVersionRepository,
    PostgresUserRepository,
)


class UnitOfWork:
    """Atomic application transaction exposing the aggregate repositories."""

    def __init__(self, db: Database) -> None:
        self._factory = db.session_factory(APPLICATION)

    def __enter__(self) -> UnitOfWork:
        self._session = self._factory()
        self.assets = PostgresAssetRepository(self._session)
        self.findings = PostgresFindingRepository(self._session)
        self.reports = PostgresReportRepository(self._session)
        self.rules = PostgresRuleVersionRepository(self._session)
        self.models = PostgresModelRegistry(self._session)
        self.users = PostgresUserRepository(self._session)
        self.runs = PostgresEngineRunRepository(self._session)
        return self

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
