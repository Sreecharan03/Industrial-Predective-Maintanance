"""Project engineer verdicts into the Knowledge Graph (ADR-016 R2).

This is the step that closes the learning loop: a hypothesis the platform raised,
once judged by an engineer, becomes part of what the graph *knows* rather than
just what it *guessed*.

The verdict is deliberately NOT written into the pattern or condition node's
properties. Those nodes are re-projected on every Phase-B run and their property
maps are replaced wholesale, so a verdict stored there would be silently erased
the next time the models ran - the failure would be invisible and the labels
would rot. Instead each verdict is its own node, linked by a VALIDATED_BY edge,
which no other projector touches.
"""

from __future__ import annotations

from senseminds.knowledge_graph.models import Edge, EdgeType, Node, NodeType
from senseminds.knowledge_graph.projector import condition_id
from senseminds.knowledge_graph.repository import KnowledgeGraphRepository
from senseminds.pattern_learning.feedback import FeedbackVerdict, HumanFeedback


def validation_id(identity_key: str) -> str:
    return f"validation:{identity_key}"


# What the verdict means for how much the platform should trust the hypothesis.
_STANDING = {
    FeedbackVerdict.CONFIRMED_NOVELTY: "confirmed",
    FeedbackVerdict.EXPECTED_BEHAVIOUR: "explained",
    FeedbackVerdict.FALSE_POSITIVE: "rejected",
}


class FeedbackProjector:
    """Fold an engineer's verdict into the graph as validated knowledge."""

    def __init__(self, repo: KnowledgeGraphRepository) -> None:
        self._repo = repo

    def project(self, feedback: HumanFeedback) -> None:
        node_id = validation_id(feedback.finding_identity_key)
        self._repo.upsert_node(
            Node(
                node_id=node_id,
                node_type=NodeType.ENGINEER_VALIDATION,
                properties={
                    "verdict": feedback.verdict.value,
                    "standing": _STANDING[feedback.verdict],
                    "author": feedback.author,
                    "note": feedback.note,
                    "reviewed_finding_id": feedback.finding_id,
                    "unit": feedback.unit,
                    "created_at": feedback.created_at.isoformat(),
                },
            )
        )
        self._repo.upsert_edge(
            Edge(
                src=condition_id(feedback.finding_identity_key),
                dst=node_id,
                edge_type=EdgeType.VALIDATED_BY,
                properties={"verdict": feedback.verdict.value},
            )
        )
