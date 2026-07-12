"""Rule Engine -> Knowledge Graph integration: DIAGNOSED findings project as
finding-conditions with TRIGGERED_BY reasoning-chain edges (ADR-015 R1)."""

from __future__ import annotations

from datetime import UTC, datetime

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
from senseminds.findings.identity import finding_id, identity_key
from senseminds.knowledge_graph import (
    EdgeType,
    InMemoryKnowledgeGraph,
    KnowledgeGraphProjector,
)
from senseminds.knowledge_graph.projector import condition_id
from senseminds.rules import DEFAULT_RULES, RuleContext, RuleEvaluator


def _derived(ftype: FindingType, target: str) -> Finding:
    idk = identity_key("SC-126", ftype, FindingScope.SENSOR, target)
    return Finding(
        finding_id=finding_id(idk, "h"), identity_key=idk, finding_type=ftype,
        category=FindingCategory.THRESHOLD, scope=FindingScope.SENSOR,
        origin=FindingOrigin.DERIVED, summary=f"{ftype.value}", detail="",
        target_key=target, equipment_key="SC-126", severity=Severity.WARNING,
        confidence=Confidence(value=0.9, rationale="t"),
        evidence=(Evidence(artifact_id="a1", description="x", observed_value=1.0),),
        source_engine="test", observed_window=ObservedWindow(),
        provenance=Provenance(engine="test", engine_version="0.1.0", source_unit="SC-126",
                              input_hash="h", produced_at=datetime(2026, 7, 10, tzinfo=UTC)),
    )


def test_diagnosed_findings_project_with_reasoning_chain() -> None:
    trigger = _derived(FindingType.THRESHOLD_MISSPECIFIED, "discharge_pressure")
    ctx = RuleContext(unit="SC-126", equipment_class="refrigeration_screw_compressor",
                      input_hash="h", observed_window=ObservedWindow())
    diagnoses = RuleEvaluator(DEFAULT_RULES).evaluate([trigger], ctx)
    assert diagnoses

    repo = InMemoryKnowledgeGraph()
    proj = KnowledgeGraphProjector(repo)
    proj.project_findings([trigger, *diagnoses])  # derived + diagnosed
    proj.project_findings([trigger, *diagnoses])  # idempotent re-projection

    diag = diagnoses[0]
    node = repo.get_node(condition_id(diag.identity_key))
    assert node is not None
    assert node.properties["origin"] == "diagnosed"
    # TRIGGERED_BY edge links the diagnosis condition to its trigger condition
    chain = [n.node_id for n in repo.neighbors(node.node_id, EdgeType.TRIGGERED_BY)]
    assert condition_id(trigger.identity_key) in chain
