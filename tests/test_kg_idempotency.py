"""Knowledge Graph projection idempotency (ADR-014 R1, mandatory).

Projecting identical inputs any number of times, in any order, must yield an
identical graph state; occurrences must never double-count; supersession across
data updates must fold deterministically.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from senseminds.application import DeterministicPipeline
from senseminds.engines.health import HealthEngine
from senseminds.findings import FindingsAssembler, ObservedWindow
from senseminds.ingestion import ProcessedCsvSource
from senseminds.knowledge_graph import (
    InMemoryKnowledgeGraph,
    KnowledgeGraphProjector,
    NodeType,
)
from senseminds.knowledge_graph.projector import condition_id


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


def _state(repo: InMemoryKnowledgeGraph):  # noqa: ANN202
    return repo.nodes(), repo.edges()


def _project(asset, findings, times: int):  # noqa: ANN202, ANN001
    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    for _ in range(times):
        proj.seed_catalog(asset)
        proj.project_findings(findings)
    return repo


def test_repeated_projection_is_identical(tmp_path: Path) -> None:
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    once = _project(asset, findings, 1)
    thrice = _project(asset, findings, 3)
    assert _state(once) == _state(thrice)
    assert once.node_count() == thrice.node_count()
    assert once.edge_count() == thrice.edge_count()


def test_occurrences_not_double_counted(tmp_path: Path) -> None:
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    repo = _project(asset, findings, 5)  # projected 5 times
    for c in repo.nodes(NodeType.FINDING_CONDITION):
        assert c.properties["occurrences"] == 1  # one distinct finding_id, not 5


def test_order_independence(tmp_path: Path) -> None:
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    forward = InMemoryKnowledgeGraph()
    KnowledgeGraphProjector(forward).seed_catalog(asset)
    KnowledgeGraphProjector(forward).project_findings(findings)
    reverse = InMemoryKnowledgeGraph()
    KnowledgeGraphProjector(reverse).seed_catalog(asset)
    KnowledgeGraphProjector(reverse).project_findings(tuple(reversed(findings)))
    assert _state(forward) == _state(reverse)


def test_supersession_across_data_updates(tmp_path: Path) -> None:
    # Two runs of the same condition (discharge pressure mis-specified) over
    # different, later data - so run B genuinely supersedes run A.
    a, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200}, "2024-01-01")
    b, _ = _findings_and_asset(tmp_path, {"Discharge Pressure": [205.0] * 200}, "2024-06-01")
    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    proj.seed_catalog(asset)
    proj.project_findings(a)
    proj.project_findings(b)

    # find a condition present in both runs (same identity_key)
    a_ids = {f.identity_key for f in a}
    b_ids = {f.identity_key for f in b}
    shared = a_ids & b_ids
    assert shared
    ident = next(iter(shared))
    node = repo.get_node(condition_id(ident))
    assert node.properties["occurrences"] == 2  # two distinct observations
    # latest_finding_id is the newer run's finding for that identity
    newer = next(f for f in b if f.identity_key == ident)
    assert node.properties["latest_finding_id"] == newer.finding_id


def test_reprojecting_same_finding_is_noop(tmp_path: Path) -> None:
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    proj.seed_catalog(asset)
    proj.project_findings(findings)
    state_1 = _state(repo)
    proj.project_findings(findings)  # again
    assert _state(repo) == state_1
