"""Analysis unit of work (ADR-019 D5) - atomicity, idempotent replay, rollback.

The whole analysis run persists (findings + KG + report + engine_run + artifacts)
in one transaction, across the application and knowledge schemas. Integration
test - skipped unless a Postgres/TimescaleDB is reachable and the processed CSVs
are present.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy
from senseminds.application.analysis_use_case import AnalysisUseCase
from senseminds.config import Settings
from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
    ObservedWindow,
)
from senseminds.infrastructure.artifact_store.base import ArtifactStore
from senseminds.infrastructure.artifact_store.local import LocalArtifactStore
from senseminds.ingestion import ProcessedCsvSource
from senseminds.knowledge_graph.models import Node, NodeType
from senseminds.repositories.models import EngineRun, RunStatus

_PROCESSED = Path(__file__).resolve().parents[2] / "Datasets" / "processed"
_UNIT = "SC-126"
_T0 = datetime(2024, 1, 1, tzinfo=UTC)


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
    not (_PROCESSED / f"{_UNIT}.csv").exists() or not _db_available(_db_url()),
    reason="TimescaleDB or processed CSV not available",
)


@pytest.fixture(scope="module")
def db():  # noqa: ANN201
    from senseminds.infrastructure.db import build_database
    from senseminds.infrastructure.db.migrate import upgrade

    url = _db_url()
    upgrade(url)
    database = build_database(Settings(database_url=url))
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


def _use_case(db, store: ArtifactStore | None = None) -> AnalysisUseCase:  # noqa: ANN001
    store = store or LocalArtifactStore(Path(tempfile.mkdtemp()))
    return AnalysisUseCase(db, store, ProcessedCsvSource(_PROCESSED))


def _uow(db):  # noqa: ANN001, ANN202
    from senseminds.infrastructure.repositories import AnalysisUnitOfWork

    return AnalysisUnitOfWork(db)


def _finding(idk: str, fid: str) -> Finding:
    return Finding(
        finding_id=fid, identity_key=idk, finding_type=FindingType.THRESHOLD_MISSPECIFIED,
        category=FindingCategory.THRESHOLD, scope=FindingScope.SENSOR, origin=FindingOrigin.DERIVED,
        summary="s", detail="d", target_key="discharge_pressure", equipment_key=_UNIT,
        severity=Severity.WARNING, confidence=Confidence(value=0.9, rationale="r"),
        evidence=(Evidence(artifact_id="a", description="e", observed_value=1.0),),
        source_engine="threshold", observed_window=ObservedWindow(start=_T0, end=_T0),
        provenance=Provenance(engine="threshold", engine_version="0.1.0", source_unit=_UNIT,
                              input_hash=fid, produced_at=_T0),
    )


# ------------------------------ atomicity -----------------------------

def test_analysis_persists_atomically(db) -> None:  # noqa: ANN001
    result = _use_case(db).run(_UNIT)
    assert result.finding_count > 0 and not result.replayed
    with _uow(db) as uow:
        assert uow.findings.count() == result.finding_count
        assert uow.runs.count() == 1
        run = uow.runs.find(_UNIT, result.input_hash)
        assert run.status is RunStatus.COMPLETED
        assert run.finding_count == result.finding_count
        assert len(run.artifact_ids) == 8  # 7 engines + health
        assert uow.reports.get(f"{_UNIT}:{result.input_hash}:daily") is not None
        assert uow.graph.node_count() > 0 and uow.graph.edge_count() > 0


# --------------------------- idempotent replay ------------------------

def test_replaying_same_input_is_a_noop(db) -> None:  # noqa: ANN001
    uc = _use_case(db)
    first = uc.run(_UNIT)
    with _uow(db) as uow:
        before = (uow.findings.count(), uow.runs.count(),
                  uow.graph.node_count(), uow.graph.edge_count())
    second = uc.run(_UNIT)  # same input hash
    assert second.replayed and second.run_id is None
    with _uow(db) as uow:
        after = (uow.findings.count(), uow.runs.count(),
                 uow.graph.node_count(), uow.graph.edge_count())
    assert after == before  # no duplicate persistent state
    assert first.input_hash == second.input_hash


# ------------------------------- rollback -----------------------------

def test_unit_of_work_rolls_back_across_both_schemas(db) -> None:  # noqa: ANN001
    # A failure mid-run must revert application (finding, engine_run) AND knowledge
    # (kg_node) writes together.
    with pytest.raises(RuntimeError), _uow(db) as uow:
        uow.runs.begin(EngineRun(run_id="r1", unit=_UNIT, input_hash="h1",
                                 status=RunStatus.RUNNING, started_at=_T0))
        uow.findings.add(_finding("id-a", "fid-1"))
        uow.graph.upsert_node(Node(node_id="equipment:SC-126", node_type=NodeType.EQUIPMENT))
        raise RuntimeError("simulated failure mid-run")
    with _uow(db) as uow:
        assert uow.findings.count() == 0       # application schema rolled back
        assert uow.runs.count() == 0
        assert uow.graph.node_count() == 0     # knowledge schema rolled back too


def test_use_case_rolls_back_on_artifact_failure(db) -> None:  # noqa: ANN001
    class _FailingStore(ArtifactStore):
        def __init__(self) -> None:
            self._n = 0

        def save(self, result: object) -> str:  # noqa: ANN401
            self._n += 1
            if self._n >= 8:  # fail on the last artifact, mid-transaction
                raise RuntimeError("artifact store failure")
            return "art"

        def load(self, artifact_id, result_type):  # noqa: ANN001, ANN201
            raise NotImplementedError

        def exists(self, artifact_id: str) -> bool:
            return False

        def list_ids(self, result_type=None):  # noqa: ANN001, ANN201
            return []

    with pytest.raises(RuntimeError):
        _use_case(db, _FailingStore()).run(_UNIT)
    with _uow(db) as uow:
        assert uow.findings.count() == 0   # nothing leaked
        assert uow.runs.count() == 0       # the 'running' engine_run row rolled back
        assert uow.graph.node_count() == 0
