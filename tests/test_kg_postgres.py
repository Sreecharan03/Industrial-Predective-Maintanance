"""PostgresKnowledgeGraph (ADR-019 D3).

Proves the persistent adapter is a behaviour-identical, swappable drop-in for the
in-memory store: same idempotency, telemetry-free, durable across a fresh repo
instance, and correct across multiple assets. Integration test - skipped unless
a Postgres/TimescaleDB is reachable (``SENSEMINDS_DATABASE_URL``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy
from senseminds.application.pipeline import DeterministicPipeline
from senseminds.config import Settings
from senseminds.engines.health import HealthEngine
from senseminds.findings import FindingsAssembler, ObservedWindow
from senseminds.ingestion import ProcessedCsvSource
from senseminds.knowledge_graph import (
    InMemoryKnowledgeGraph,
    KnowledgeGraphProjector,
    NodeType,
)
from senseminds.knowledge_graph.projector import equipment_id

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
    not _db_available(_db_url()), reason="TimescaleDB not available"
)


def _findings_and_asset(tmp_path: Path, values: dict[str, list], start: str = "2024-01-01"):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range(start, periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    ctx = DeterministicPipeline().run(ProcessedCsvSource(tmp_path).load("SC-126"))
    health = HealthEngine().compute(ctx)
    window = ObservedWindow(start=ctx.series.manifest.start, end=ctx.series.manifest.end)
    subsystem_of = {k: sub.key for sub in ctx.series.asset.subsystems for k in sub.sensor_keys}
    findings = FindingsAssembler().assemble(
        threshold=ctx.threshold, reliability=ctx.reliability, health=health,
        observed_window=window, subsystem_of=subsystem_of,
    )
    return findings, ctx.series.asset


@pytest.fixture(scope="module")
def db():  # noqa: ANN201
    from senseminds.infrastructure.db import build_database
    from senseminds.infrastructure.db.migrate import upgrade

    url = _db_url()
    upgrade(url)  # idempotent
    database = build_database(Settings(database_url=url))
    yield database
    database.dispose()


@pytest.fixture
def pg(db):  # noqa: ANN001, ANN201
    from senseminds.infrastructure.db import KNOWLEDGE
    from senseminds.infrastructure.graph_store import PostgresKnowledgeGraph

    with db.session(KNOWLEDGE) as session:
        session.execute(sqlalchemy.text("TRUNCATE knowledge.kg_edge, knowledge.kg_node"))
    return PostgresKnowledgeGraph(db)


def _project(repo, asset, findings) -> None:  # noqa: ANN001
    proj = KnowledgeGraphProjector(repo)
    proj.seed_catalog(asset)
    proj.project_findings(findings)


def test_postgres_is_behaviour_identical_to_inmemory(pg, tmp_path: Path) -> None:  # noqa: ANN001
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    mem = InMemoryKnowledgeGraph()
    _project(mem, asset, findings)
    _project(pg, asset, findings)
    assert pg.nodes() == mem.nodes()  # ids, types AND properties
    assert pg.edges() == mem.edges()
    assert (pg.node_count(), pg.edge_count()) == (mem.node_count(), mem.edge_count())


def test_repeated_projection_is_idempotent(pg, tmp_path: Path) -> None:  # noqa: ANN001
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    _project(pg, asset, findings)
    once = (pg.nodes(), pg.edges())
    for _ in range(3):
        _project(pg, asset, findings)
    assert (pg.nodes(), pg.edges()) == once  # identical graph, no duplicates
    for cond in pg.nodes(NodeType.FINDING_CONDITION):
        assert cond.properties["occurrences"] == 1  # one distinct finding_id, not 4


def test_durable_across_fresh_repo_instance(pg, db, tmp_path: Path) -> None:  # noqa: ANN001
    from senseminds.infrastructure.graph_store import PostgresKnowledgeGraph

    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    _project(pg, asset, findings)
    before = (pg.nodes(), pg.edges())

    # A brand-new repo object holds no in-process state: what it reads proves the
    # graph lives in Postgres (the app-level proxy for a container restart).
    reloaded = PostgresKnowledgeGraph(db)
    assert (reloaded.nodes(), reloaded.edges()) == before
    _project(reloaded, asset, findings)  # re-project == complete no-op
    assert (reloaded.nodes(), reloaded.edges()) == before


def test_telemetry_free(pg, tmp_path: Path) -> None:  # noqa: ANN001
    # No node/edge property may carry a raw time series (only knowledge + refs).
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    _project(pg, asset, findings)
    for node in pg.nodes():
        for value in node.properties.values():
            assert not (isinstance(value, list) and len(value) > 50)  # no series blobs


@pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not (_PROCESSED / "SC-114.csv").exists(),
    reason="processed CSVs for two units not available",
)
def test_multi_asset_isolation(pg) -> None:  # noqa: ANN001
    csv = ProcessedCsvSource(_PROCESSED)
    per_unit_nodes = {}
    for unit in ("SC-126", "SC-114"):
        asset = csv.load(unit).asset
        KnowledgeGraphProjector(pg).seed_catalog(asset)
        per_unit_nodes[unit] = asset

    equipment = [n.node_id for n in pg.nodes(NodeType.EQUIPMENT)]
    assert equipment == sorted([equipment_id("SC-114"), equipment_id("SC-126")])
    # each equipment's subsystem neighbours belong only to that unit
    for unit in ("SC-126", "SC-114"):
        neighbours = pg.neighbors(equipment_id(unit))
        assert neighbours  # has subsystems
        assert all(unit in n.node_id for n in neighbours)  # no cross-asset leakage
