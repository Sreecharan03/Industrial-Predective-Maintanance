"""Analysis concurrency (ADR-019 D5).

Fire many analysis requests at once - same asset and different assets - and prove
transaction isolation holds: no duplicate findings, no duplicate graph
projection, exactly one engine-run per (unit, input_hash), consistent counts.
Integration test - skipped unless a Postgres/TimescaleDB and processed CSVs are
present.
"""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import sqlalchemy
from senseminds.application.analysis_use_case import AnalysisUseCase
from senseminds.config import Settings
from senseminds.infrastructure.artifact_store.local import LocalArtifactStore
from senseminds.ingestion import ProcessedCsvSource

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
    not (_PROCESSED / "SC-126.csv").exists()
    or not (_PROCESSED / "SC-114.csv").exists()
    or not _db_available(_db_url()),
    reason="TimescaleDB or processed CSVs not available",
)


@pytest.fixture(scope="module")
def db():  # noqa: ANN201
    from senseminds.infrastructure.db import build_database
    from senseminds.infrastructure.db.migrate import upgrade

    upgrade(_db_url())
    # a pool large enough for the concurrent sessions
    database = build_database(Settings(database_url=_db_url()))
    yield database
    database.dispose()


@pytest.fixture(autouse=True)
def _clean(db):  # noqa: ANN001, ANN202
    from senseminds.infrastructure.db import APPLICATION, KNOWLEDGE

    with db.session(APPLICATION) as s:
        s.execute(sqlalchemy.text(
            "TRUNCATE application.finding, application.report, application.engine_run, "
            "application.asset"))
    with db.session(KNOWLEDGE) as s:
        s.execute(sqlalchemy.text("TRUNCATE knowledge.kg_edge, knowledge.kg_node"))
    yield


def _use_case(db) -> AnalysisUseCase:  # noqa: ANN001
    return AnalysisUseCase(db, LocalArtifactStore(Path(tempfile.mkdtemp())),
                           ProcessedCsvSource(_PROCESSED))


def _uow(db):  # noqa: ANN001, ANN202
    from senseminds.infrastructure.repositories import AnalysisUnitOfWork

    return AnalysisUnitOfWork(db)


def test_concurrent_same_asset_has_exactly_one_run(db) -> None:  # noqa: ANN001
    uc = _use_case(db)
    n = 5
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(lambda _: uc.run("SC-126"), range(n)))

    owners = [r for r in results if not r.replayed]
    assert len(owners) == 1  # exactly one request persisted; the rest were no-ops
    owner = owners[0]
    with _uow(db) as uow:
        assert uow.runs.count() == 1                          # no duplicate engine_run
        assert uow.findings.count() == owner.finding_count    # no duplicate findings
        # graph equals a single clean projection of this asset
        equipment = [nd.node_id for nd in uow.graph.nodes()
                     if nd.node_id.startswith("equipment:")]
        assert equipment == ["equipment:SC-126"]


def test_concurrent_different_assets_are_isolated(db) -> None:  # noqa: ANN001
    uc = _use_case(db)
    units = ["SC-126", "SC-114"]
    with ThreadPoolExecutor(max_workers=len(units)) as pool:
        results = list(pool.map(uc.run, units))

    assert all(not r.replayed for r in results)  # different keys -> all persisted
    with _uow(db) as uow:
        assert uow.runs.count() == len(units)
        total = sum(r.finding_count for r in results)
        assert uow.findings.count() == total
        for unit in units:
            unit_findings = uow.findings.for_unit(unit)
            assert unit_findings and all(f.equipment_key == unit for f in unit_findings)
        equipment = sorted(nd.node_id for nd in uow.graph.nodes()
                           if nd.node_id.startswith("equipment:"))
        assert equipment == ["equipment:SC-114", "equipment:SC-126"]


def test_concurrent_mixed_load_stays_consistent(db) -> None:  # noqa: ANN001
    # Several requests for each of two assets, all at once.
    uc = _use_case(db)
    jobs = ["SC-126", "SC-114", "SC-126", "SC-114", "SC-126", "SC-114"]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(uc.run, jobs))

    owners_by_unit: dict[str, int] = {}
    for r in results:
        if not r.replayed:
            owners_by_unit[r.unit] = owners_by_unit.get(r.unit, 0) + 1
    assert owners_by_unit == {"SC-126": 1, "SC-114": 1}  # one persisted run per asset
    with _uow(db) as uow:
        assert uow.runs.count() == 2
