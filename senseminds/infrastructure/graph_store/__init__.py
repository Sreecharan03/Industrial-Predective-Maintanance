"""Persistent knowledge-graph adapters (ADR-019 D3).

`PostgresKnowledgeGraph` implements the same `KnowledgeGraphRepository` interface
as the in-memory store, so the projector and every consumer are unaware of the
backing store - a future Neo4j adapter slots in the same way.
"""

from senseminds.infrastructure.graph_store.postgres import PostgresKnowledgeGraph

__all__ = ["PostgresKnowledgeGraph"]
