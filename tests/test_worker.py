"""Analysis worker (Platform Integration) - cycle + idempotency.

Integration test - skipped unless a Postgres/TimescaleDB and processed CSVs are
present.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import sqlalchemy
from senseminds.config import Settings

_PROCESSED = Path(__file__).resolve().parents[2] / "Datasets" / "processed"


def _db_url() -> str:
    return os.environ.get("SENSEMINDS_DATABASE_URL") or Settings().database_url


def _db_available(url: str) -> bool:
    try:
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _db_available(_db_url()),
    reason="TimescaleDB or processed CSV not available",
)


def test_worker_cycle_runs_then_is_idempotent() -> None:
    from senseminds.application.analysis_use_case import AnalysisUseCase
    from senseminds.application.bootstrap import bootstrap_units
    from senseminds.infrastructure.artifact_store.local import LocalArtifactStore
    from senseminds.infrastructure.db import APPLICATION, KNOWLEDGE, build_database
    from senseminds.infrastructure.db.migrate import upgrade
    from senseminds.ingestion import DbTimeSeriesSource
    from senseminds.workers import AnalysisWorker

    upgrade(_db_url())
    db = build_database(Settings(database_url=_db_url()))
    bootstrap_units(db, _PROCESSED, units=["SC-126"])
    with db.session(APPLICATION) as s:
        s.execute(sqlalchemy.text(
            "TRUNCATE application.finding, application.report, application.engine_run, "
            "application.asset"))
    with db.session(KNOWLEDGE) as s:
        s.execute(sqlalchemy.text("TRUNCATE knowledge.kg_edge, knowledge.kg_node"))

    source = DbTimeSeriesSource(db)
    use_case = AnalysisUseCase(db, LocalArtifactStore(Path(tempfile.mkdtemp())), source)
    worker = AnalysisWorker(use_case, source, interval_seconds=1, units=["SC-126"])

    first = worker.run_once()
    assert len(first) == 1 and not first[0].replayed and first[0].finding_count > 0

    second = worker.run_once()  # same accumulated data -> idempotent no-op
    assert second[0].replayed is True
    db.dispose()
