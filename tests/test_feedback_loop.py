"""The label-bootstrap loop: storage semantics, KG projection, and the edge cases.

These pin the decisions that make a verdict usable as a training label later:
it is keyed on the condition (not one observation of it), a changed mind is
recorded rather than overwritten, a double-click does not fabricate a second
label, and a verdict written into the graph is not erased by the next Phase-B run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from senseminds.knowledge_graph import FeedbackProjector
from senseminds.knowledge_graph.feedback_projector import validation_id
from senseminds.knowledge_graph.memory_store import InMemoryKnowledgeGraph
from senseminds.knowledge_graph.models import EdgeType, NodeType
from senseminds.knowledge_graph.projector import condition_id
from senseminds.pattern_learning.feedback import (
    FeedbackVerdict,
    HumanFeedback,
    InMemoryFeedbackRepository,
)

NOW = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


def _fb(
    identity: str = "idk1",
    verdict: FeedbackVerdict = FeedbackVerdict.CONFIRMED_NOVELTY,
    author: str = "engineer_a",
    at: datetime = NOW,
    note: str = "",
    finding_id: str = "f-1",
) -> HumanFeedback:
    return HumanFeedback(
        feedback_id=f"{identity}-{author}-{verdict.value}-{at.isoformat()}",
        finding_identity_key=identity,
        finding_id=finding_id,
        unit="SC-126",
        verdict=verdict,
        author=author,
        note=note,
        created_at=at,
    )


class TestModel:
    def test_verdict_is_keyed_on_the_condition_not_the_observation(self) -> None:
        """The same condition observed twice keeps ONE identity - so a verdict
        given on Monday still applies to Tuesday's observation of it."""
        monday = _fb(finding_id="finding-monday")
        tuesday = _fb(finding_id="finding-tuesday", at=NOW + timedelta(days=1))
        assert monday.finding_identity_key == tuesday.finding_identity_key
        assert monday.finding_id != tuesday.finding_id

    def test_reviewed_observation_is_retained_for_audit(self) -> None:
        assert _fb(finding_id="finding-xyz").finding_id == "finding-xyz"

    def test_legacy_construction_without_persistence_fields_still_works(self) -> None:
        """The in-memory port predates the store; it must not have been broken."""
        fb = HumanFeedback(
            finding_identity_key="idk", verdict=FeedbackVerdict.FALSE_POSITIVE,
            author="engineer", created_at=NOW,
        )
        assert fb.feedback_id == "" and fb.unit == ""


class TestInMemoryPort:
    def test_records_and_reads_back(self) -> None:
        repo = InMemoryFeedbackRepository()
        repo.record(_fb())
        assert len(repo.for_finding("idk1")) == 1
        assert repo.for_finding("other") == []

    def test_disagreement_between_engineers_is_preserved(self) -> None:
        repo = InMemoryFeedbackRepository()
        repo.record(_fb(author="engineer_a", verdict=FeedbackVerdict.CONFIRMED_NOVELTY))
        repo.record(_fb(author="engineer_b", verdict=FeedbackVerdict.FALSE_POSITIVE,
                        at=NOW + timedelta(minutes=5)))
        verdicts = {f.author: f.verdict for f in repo.for_finding("idk1")}
        assert verdicts["engineer_a"] is FeedbackVerdict.CONFIRMED_NOVELTY
        assert verdicts["engineer_b"] is FeedbackVerdict.FALSE_POSITIVE


class TestKnowledgeGraphProjection:
    """The 'system becomes smarter' step — and the trap it has to avoid."""

    def test_verdict_becomes_a_validation_node_linked_to_the_condition(self) -> None:
        graph = InMemoryKnowledgeGraph()
        FeedbackProjector(graph).project(_fb())

        node = graph.get_node(validation_id("idk1"))
        assert node is not None
        assert node.node_type is NodeType.ENGINEER_VALIDATION
        assert node.properties["verdict"] == "confirmed_novelty"
        assert node.properties["standing"] == "confirmed"
        assert node.properties["author"] == "engineer_a"

        edges = graph.edges(edge_type=EdgeType.VALIDATED_BY,
                            src=condition_id("idk1"))
        assert len(edges) == 1
        assert edges[0].dst == validation_id("idk1")

    @pytest.mark.parametrize(
        ("verdict", "standing"),
        [
            (FeedbackVerdict.CONFIRMED_NOVELTY, "confirmed"),
            (FeedbackVerdict.EXPECTED_BEHAVIOUR, "explained"),
            (FeedbackVerdict.FALSE_POSITIVE, "rejected"),
        ],
    )
    def test_every_verdict_maps_to_a_standing(
        self, verdict: FeedbackVerdict, standing: str
    ) -> None:
        graph = InMemoryKnowledgeGraph()
        FeedbackProjector(graph).project(_fb(verdict=verdict))
        assert graph.get_node(validation_id("idk1")).properties["standing"] == standing

    def test_changed_verdict_replaces_the_standing(self) -> None:
        graph = InMemoryKnowledgeGraph()
        p = FeedbackProjector(graph)
        p.project(_fb(verdict=FeedbackVerdict.CONFIRMED_NOVELTY))
        p.project(_fb(verdict=FeedbackVerdict.FALSE_POSITIVE, at=NOW + timedelta(hours=1)))
        node = graph.get_node(validation_id("idk1"))
        assert node.properties["standing"] == "rejected"   # graph shows what is CURRENT
        assert len(graph.edges(edge_type=EdgeType.VALIDATED_BY,
                               src=condition_id("idk1"))) == 1   # not duplicated

    def test_validation_survives_a_pattern_reprojection(self) -> None:
        """THE regression this design exists to prevent.

        Pattern/condition nodes are re-upserted on every Phase-B run with their
        properties REPLACED. A verdict stored on those nodes would vanish. It
        lives on its own node, so a re-projection cannot touch it."""
        from senseminds.knowledge_graph.models import Node

        graph = InMemoryKnowledgeGraph()
        FeedbackProjector(graph).project(_fb())

        # simulate the next Phase-B run rewriting the condition node wholesale
        graph.upsert_node(Node(
            node_id=condition_id("idk1"),
            node_type=NodeType.FINDING_CONDITION,
            properties={"origin": "learned", "status": "hypothesis"},  # no verdict
        ))

        node = graph.get_node(validation_id("idk1"))
        assert node is not None, "the engineer's verdict was erased by a model re-run"
        assert node.properties["standing"] == "confirmed"
        assert graph.edges(edge_type=EdgeType.VALIDATED_BY,
                           src=condition_id("idk1"))

    def test_two_conditions_get_independent_validations(self) -> None:
        graph = InMemoryKnowledgeGraph()
        p = FeedbackProjector(graph)
        p.project(_fb(identity="idk1", verdict=FeedbackVerdict.CONFIRMED_NOVELTY))
        p.project(_fb(identity="idk2", verdict=FeedbackVerdict.FALSE_POSITIVE))
        assert graph.get_node(validation_id("idk1")).properties["standing"] == "confirmed"
        assert graph.get_node(validation_id("idk2")).properties["standing"] == "rejected"
