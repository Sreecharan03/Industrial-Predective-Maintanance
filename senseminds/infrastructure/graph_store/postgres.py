"""PostgreSQL-backed knowledge graph (ADR-019 D3).

A drop-in `KnowledgeGraphRepository` whose behaviour is identical to
`InMemoryKnowledgeGraph`:

* **Idempotent** - ``upsert_node`` keys by ``node_id``; ``upsert_edge`` keys by
  ``(src, dst, edge_type)`` via ``ON CONFLICT DO UPDATE``. Re-projecting the same
  findings produces the identical graph with no duplicate rows.
* **Deterministic queries** - ``nodes()`` ordered by ``node_id``; ``edges()`` by
  ``(src, dst, edge_type)``; ``neighbors()`` returns distinct existing targets in
  sorted order - matching the in-memory store exactly.
* **Telemetry-free** - only knowledge entities + their JSON-serialisable
  properties are stored (ADR-014); raw readings/statistics stay in TimescaleDB /
  artifacts.

Properties are serialised with ``sort_keys`` so the stored JSONB is canonical and
byte-stable across identical projections. Each write commits in its own
transaction, so a read immediately sees a prior write - the read-then-fold the
projector relies on for occurrence de-duplication.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from senseminds.infrastructure.db import KNOWLEDGE, Database
from senseminds.knowledge_graph.models import Edge, EdgeType, Node, NodeType
from senseminds.knowledge_graph.repository import KnowledgeGraphRepository

_UPSERT_NODE = text(
    """
    INSERT INTO knowledge.kg_node (node_id, node_type, properties, updated_at)
    VALUES (:node_id, :node_type, CAST(:properties AS JSONB), now())
    ON CONFLICT (node_id) DO UPDATE
        SET node_type = EXCLUDED.node_type,
            properties = EXCLUDED.properties,
            updated_at = now()
    """
)
_UPSERT_EDGE = text(
    """
    INSERT INTO knowledge.kg_edge (src, dst, edge_type, properties, updated_at)
    VALUES (:src, :dst, :edge_type, CAST(:properties AS JSONB), now())
    ON CONFLICT (src, dst, edge_type) DO UPDATE
        SET properties = EXCLUDED.properties,
            updated_at = now()
    """
)


def _props(value: object) -> dict[str, object]:
    """JSONB comes back as a parsed dict (psycopg) or a JSON string; normalise."""
    if isinstance(value, str):
        return json.loads(value)
    return dict(value) if value else {}


class PostgresKnowledgeGraph(KnowledgeGraphRepository):
    """Relational knowledge-graph store behind the repository interface.

    Two modes, same behaviour: standalone (``db``) opens a fresh transaction per
    call - immediate visibility for the projector's read-then-fold, as in D3; or
    **bound** (``session``) joins a caller's transaction and never commits, so a
    KG projection can be part of a larger atomic unit of work (D5). Consumers and
    the projector are unaware of which mode is in use.
    """

    def __init__(self, db: Database | None = None, *, session: Session | None = None) -> None:
        if (db is None) == (session is None):
            raise ValueError("provide exactly one of `db` or `session`")
        self._db = db
        self._session = session

    @contextmanager
    def _exec(self) -> Iterator[Session]:
        if self._session is not None:
            yield self._session  # bound to a caller transaction: no commit/close here
        else:
            with self._db.session(KNOWLEDGE) as session:  # type: ignore[union-attr]
                yield session

    # ------------------------------- writes -------------------------------
    def upsert_node(self, node: Node) -> None:
        with self._exec() as session:
            session.execute(
                _UPSERT_NODE,
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type.value,
                    "properties": json.dumps(node.properties, sort_keys=True, default=str),
                },
            )

    def upsert_edge(self, edge: Edge) -> None:
        with self._exec() as session:
            session.execute(
                _UPSERT_EDGE,
                {
                    "src": edge.src,
                    "dst": edge.dst,
                    "edge_type": edge.edge_type.value,
                    "properties": json.dumps(edge.properties, sort_keys=True, default=str),
                },
            )

    # ------------------------------- reads --------------------------------
    def get_node(self, node_id: str) -> Node | None:
        with self._exec() as session:
            row = session.execute(
                text("SELECT node_id, node_type, properties FROM knowledge.kg_node "
                     "WHERE node_id = :node_id"),
                {"node_id": node_id},
            ).one_or_none()
        return self._node(row) if row is not None else None

    def has_node(self, node_id: str) -> bool:
        with self._exec() as session:
            return session.execute(
                text("SELECT 1 FROM knowledge.kg_node WHERE node_id = :node_id"),
                {"node_id": node_id},
            ).first() is not None

    def nodes(self, node_type: NodeType | None = None) -> list[Node]:
        sql = "SELECT node_id, node_type, properties FROM knowledge.kg_node"
        params: dict[str, object] = {}
        if node_type is not None:
            sql += " WHERE node_type = :node_type"
            params["node_type"] = node_type.value
        sql += " ORDER BY node_id"
        with self._exec() as session:
            return [self._node(r) for r in session.execute(text(sql), params)]

    def edges(self, edge_type: EdgeType | None = None, src: str | None = None) -> list[Edge]:
        sql = "SELECT src, dst, edge_type, properties FROM knowledge.kg_edge"
        clauses: list[str] = []
        params: dict[str, object] = {}
        if edge_type is not None:
            clauses.append("edge_type = :edge_type")
            params["edge_type"] = edge_type.value
        if src is not None:
            clauses.append("src = :src")
            params["src"] = src
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY src, dst, edge_type"
        with self._exec() as session:
            return [self._edge(r) for r in session.execute(text(sql), params)]

    def neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[Node]:
        dst_ids = sorted({e.dst for e in self.edges(edge_type=edge_type, src=node_id)})
        nodes = (self.get_node(d) for d in dst_ids)
        return [n for n in nodes if n is not None]

    def node_count(self) -> int:
        with self._exec() as session:
            return int(session.execute(text("SELECT count(*) FROM knowledge.kg_node")).scalar_one())

    def edge_count(self) -> int:
        with self._exec() as session:
            return int(session.execute(text("SELECT count(*) FROM knowledge.kg_edge")).scalar_one())

    # ------------------------------ mapping -------------------------------
    @staticmethod
    def _node(row: Row) -> Node:
        return Node(node_id=row[0], node_type=NodeType(row[1]), properties=_props(row[2]))

    @staticmethod
    def _edge(row: Row) -> Edge:
        return Edge(src=row[0], dst=row[1], edge_type=EdgeType(row[2]), properties=_props(row[3]))
