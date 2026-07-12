"""Analysis unit of work (ADR-019 D5).

One session, one transaction, spanning every store an analysis run writes:
findings, reports, model metadata, the engine-run record (application schema) AND
the Knowledge Graph projection (knowledge schema). Because all schemas live in one
Postgres instance today, a single connection makes the whole run atomic - it all
commits or it all rolls back.

R4 reconciliation: R4 keeps the schemas physically separable (no cross-schema
FKs, per-store session factories). This atomic cross-schema transaction is a
*deployment-time* choice enabled by co-location; if the knowledge store is later
split to its own database, the AnalysisUseCase degrades to R4's stated fallback -
commit the application transaction, then idempotently (re-)project the graph -
with no change to the projector, engines, or repositories.
"""

from __future__ import annotations

from types import TracebackType

from senseminds.infrastructure.db import APPLICATION, Database
from senseminds.infrastructure.graph_store import PostgresKnowledgeGraph
from senseminds.infrastructure.repositories.postgres import (
    PostgresAssetRepository,
    PostgresEngineRunRepository,
    PostgresFindingRepository,
    PostgresModelRegistry,
    PostgresReportRepository,
    PostgresRuleVersionRepository,
    PostgresUserRepository,
)


class AnalysisUnitOfWork:
    """Atomic transaction for a whole analysis run (all stores, one commit)."""

    def __init__(self, db: Database) -> None:
        # One session/connection; a single Postgres transaction reaches every
        # schema in this instance.
        self._factory = db.session_factory(APPLICATION)

    def __enter__(self) -> AnalysisUnitOfWork:
        self._session = self._factory()
        self.assets = PostgresAssetRepository(self._session)
        self.findings = PostgresFindingRepository(self._session)
        self.reports = PostgresReportRepository(self._session)
        self.rules = PostgresRuleVersionRepository(self._session)
        self.models = PostgresModelRegistry(self._session)
        self.users = PostgresUserRepository(self._session)
        self.runs = PostgresEngineRunRepository(self._session)
        # Bound to the SAME session -> the graph projection is part of this txn.
        self.graph = PostgresKnowledgeGraph(session=self._session)
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
