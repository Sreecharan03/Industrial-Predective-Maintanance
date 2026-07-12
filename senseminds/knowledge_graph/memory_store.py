"""Embedded in-memory knowledge graph.

Zero-ops, versionable, fully deterministic implementation of
`KnowledgeGraphRepository` for single-plant use (ADR-005). Upserts key nodes by
id and edges by (src, dst, type), so repeated writes never duplicate. Queries
return results in sorted order for reproducibility. Swappable for Neo4j behind
the same interface.
"""

from __future__ import annotations

from senseminds.knowledge_graph.models import Edge, EdgeType, Node, NodeType
from senseminds.knowledge_graph.repository import KnowledgeGraphRepository


class InMemoryKnowledgeGraph(KnowledgeGraphRepository):
    """Dict-backed graph store."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[str, str, str], Edge] = {}

    def upsert_node(self, node: Node) -> None:
        self._nodes[node.node_id] = node

    def upsert_edge(self, edge: Edge) -> None:
        self._edges[edge.key] = edge

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def nodes(self, node_type: NodeType | None = None) -> list[Node]:
        items = [n for n in self._nodes.values() if node_type is None or n.node_type is node_type]
        return sorted(items, key=lambda n: n.node_id)

    def edges(self, edge_type: EdgeType | None = None, src: str | None = None) -> list[Edge]:
        items = [
            e
            for e in self._edges.values()
            if (edge_type is None or e.edge_type is edge_type) and (src is None or e.src == src)
        ]
        return sorted(items, key=lambda e: e.key)

    def neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[Node]:
        dst_ids = [e.dst for e in self.edges(edge_type=edge_type, src=node_id)]
        return [self._nodes[d] for d in sorted(set(dst_ids)) if d in self._nodes]

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)
