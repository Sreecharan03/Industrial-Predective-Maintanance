"""Knowledge-graph repository port (ADR-005/014).

The interface inner layers depend on. An embedded in-memory store implements it
now; Neo4j (or another graph DB) can implement the same contract later without
touching the projector or any consumer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from senseminds.knowledge_graph.models import Edge, EdgeType, Node, NodeType


class KnowledgeGraphRepository(ABC):
    """Persist and query knowledge-graph nodes and edges."""

    @abstractmethod
    def upsert_node(self, node: Node) -> None:
        """Insert or replace a node (keyed by node_id)."""

    @abstractmethod
    def upsert_edge(self, edge: Edge) -> None:
        """Insert or replace an edge (keyed by src, dst, type)."""

    @abstractmethod
    def get_node(self, node_id: str) -> Node | None: ...

    @abstractmethod
    def has_node(self, node_id: str) -> bool: ...

    @abstractmethod
    def nodes(self, node_type: NodeType | None = None) -> list[Node]:
        """All nodes (sorted by id), optionally filtered by type."""

    @abstractmethod
    def edges(self, edge_type: EdgeType | None = None, src: str | None = None) -> list[Edge]:
        """All edges (sorted), optionally filtered by type and/or source."""

    @abstractmethod
    def neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[Node]:
        """Destination nodes reachable from node_id (optionally by edge type)."""

    @abstractmethod
    def node_count(self) -> int: ...

    @abstractmethod
    def edge_count(self) -> int: ...
