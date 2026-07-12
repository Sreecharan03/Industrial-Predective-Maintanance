"""Knowledge Graph - behaviour, contract, and SC-126 projection tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from senseminds.application import DeterministicPipeline
from senseminds.engines.health import HealthEngine
from senseminds.findings import FindingsAssembler, ObservedWindow
from senseminds.ingestion import ProcessedCsvSource
from senseminds.knowledge_graph import (
    Edge,
    EdgeType,
    InMemoryKnowledgeGraph,
    KnowledgeGraphProjector,
    Node,
    NodeType,
)
from senseminds.knowledge_graph.projector import condition_id, equipment_id, sensor_id

_ALLOWED_NODE_TYPES = set(NodeType)


def _findings_and_asset(tmp_path: Path, values: dict[str, list]):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
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


# ----------------------------- behaviour -----------------------------

def test_seed_catalog_creates_structure(tmp_path: Path) -> None:
    _, asset = _findings_and_asset(tmp_path, {"Suction Pressure": [20.0] * 100})
    repo = InMemoryKnowledgeGraph()
    KnowledgeGraphProjector(repo).seed_catalog(asset)
    assert repo.has_node(equipment_id("SC-126"))
    assert repo.nodes(NodeType.SUBSYSTEM)  # subsystems present
    # equipment -> subsystem -> sensor structural chain exists
    subs = repo.neighbors(equipment_id("SC-126"), EdgeType.HAS_SUBSYSTEM)
    assert subs
    sensors = repo.neighbors(subs[0].node_id, EdgeType.HAS_SENSOR)
    assert sensors


def test_project_findings_creates_condition_and_links(tmp_path: Path) -> None:
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    proj.seed_catalog(asset)
    proj.project_findings(findings)

    conditions = repo.nodes(NodeType.FINDING_CONDITION)
    assert conditions
    c = conditions[0]
    assert c.properties["occurrences"] == 1
    assert c.properties["status"] == "active"
    # OBSERVED_ON links the condition to its target entity
    assert repo.neighbors(c.node_id, EdgeType.OBSERVED_ON)
    # HAS_EVIDENCE links to an artifact ref carrying the observed value
    ev_edges = repo.edges(EdgeType.HAS_EVIDENCE, src=c.node_id)
    assert ev_edges and "observed_value" in ev_edges[0].properties


def test_graph_stores_no_telemetry(tmp_path: Path) -> None:
    findings, asset = _findings_and_asset(tmp_path, {"Discharge Pressure": [200.0] * 200})
    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    proj.seed_catalog(asset)
    proj.project_findings(findings)
    # every node is a knowledge/structure type - never a raw value/reading node
    assert all(n.node_type in _ALLOWED_NODE_TYPES for n in repo.nodes())


# ----------------------------- contract -----------------------------

def test_node_is_immutable_and_serializable() -> None:
    node = Node(
        node_id="equipment:SC-126", node_type=NodeType.EQUIPMENT, properties={"key": "SC-126"}
    )
    with pytest.raises(ValidationError):
        node.node_id = "x"  # type: ignore[misc]
    assert Node.model_validate_json(node.model_dump_json()) == node


def test_edge_identity_and_upsert_dedups() -> None:
    repo = InMemoryKnowledgeGraph()
    e = Edge(src="a", dst="b", edge_type=EdgeType.HAS_SENSOR)
    repo.upsert_edge(e)
    repo.upsert_edge(e)  # same key -> no duplicate
    assert repo.edge_count() == 1


# ----------------------------- SC-126 projection ---------------------

@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "Datasets" / "processed" / "SC-126.csv").exists(),
    reason="Phase-1/2 data not available",
)
def test_sc126_projection_has_threshold_misspecified_condition() -> None:
    processed = Path(__file__).resolve().parents[2] / "Datasets" / "processed"
    ctx = DeterministicPipeline().run(ProcessedCsvSource(processed).load("SC-126"))
    health = HealthEngine().compute(ctx)
    window = ObservedWindow(start=ctx.series.manifest.start, end=ctx.series.manifest.end)
    subsystem_of = {k: sub.key for sub in ctx.series.asset.subsystems for k in sub.sensor_keys}
    findings = FindingsAssembler().assemble(
        threshold=ctx.threshold, reliability=ctx.reliability, health=health,
        observed_window=window, subsystem_of=subsystem_of,
    )
    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    proj.seed_catalog(ctx.series.asset)
    proj.project_findings(findings)

    dp = next(f for f in findings if f.target_key == "discharge_pressure"
              and f.finding_type.value == "threshold_misspecified")
    node = repo.get_node(condition_id(dp.identity_key))
    assert node is not None
    # the condition is linked to the actual sensor node
    targets = [n.node_id for n in repo.neighbors(node.node_id, EdgeType.OBSERVED_ON)]
    assert sensor_id("SC-126", "discharge_pressure") in targets
