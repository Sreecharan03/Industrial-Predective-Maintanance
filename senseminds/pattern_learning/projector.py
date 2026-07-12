"""Project LEARNED outputs into the Knowledge Graph as hypotheses (ADR-016 §9).

Learned findings become FindingCondition nodes with ``origin=learned``; each
DiscoveredPattern becomes a node with ``status=hypothesis`` linked to its model
(DISCOVERED_BY) and to the finding that surfaced it (SUGGESTS). Idempotent, and
cleanly separable from deterministic facts by node type / origin / status.
"""

from __future__ import annotations

from senseminds.knowledge_graph.models import Edge, EdgeType, Node, NodeType
from senseminds.knowledge_graph.projector import KnowledgeGraphProjector, condition_id
from senseminds.knowledge_graph.repository import KnowledgeGraphRepository
from senseminds.pattern_learning.models import PatternResult


class PatternProjector:
    """Fold a PatternResult into the graph as quarantined hypotheses."""

    def __init__(self, repo: KnowledgeGraphRepository) -> None:
        self._repo = repo
        self._findings = KnowledgeGraphProjector(repo)

    def project(self, result: PatternResult) -> None:
        model_node = f"model:{result.model_id}@{result.model_version}"
        self._repo.upsert_node(
            Node(
                node_id=model_node,
                node_type=NodeType.LEARNED_MODEL,
                properties={"model_id": result.model_id, "version": result.model_version},
            )
        )
        for p in result.patterns:
            self._repo.upsert_node(
                Node(
                    node_id=p.pattern_id,
                    node_type=NodeType.DISCOVERED_PATTERN,
                    properties={
                        "kind": p.kind,
                        "label": p.label,
                        "support_windows": p.support_windows,
                        "confidence": p.confidence,
                        "lifecycle": p.lifecycle.value,
                        "status": p.status,
                    },
                )
            )
            self._repo.upsert_edge(
                Edge(
                    src=p.pattern_id,
                    dst=model_node,
                    edge_type=EdgeType.DISCOVERED_BY,
                    properties={"confidence": p.confidence},
                )
            )

        # learned findings -> FindingConditions (origin=learned), then SUGGESTS edges
        self._findings.project_findings(result.findings)
        for f in result.findings:
            cond = condition_id(f.identity_key)
            for p in result.patterns:
                self._repo.upsert_edge(
                    Edge(
                        src=cond,
                        dst=p.pattern_id,
                        edge_type=EdgeType.SUGGESTS,
                        properties={"confidence": p.confidence, "status": "hypothesis"},
                    )
                )
