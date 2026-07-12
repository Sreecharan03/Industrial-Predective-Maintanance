"""knowledge graph: kg_node + kg_edge (ADR-019 D3)

Revision ID: 0002_knowledge_graph
Revises: 0001_baseline
Create Date: 2026-07-12

Persistent backing for the KnowledgeGraphRepository. Node identity = node_id;
edge identity = (src, dst, edge_type) - matching the in-memory store's upsert
keys exactly, so idempotency is preserved. Properties are JSONB (knowledge only,
telemetry-free per ADR-014).

No FK from kg_edge to kg_node **by design**: the in-memory store tolerates edges
whose endpoints are not (yet) nodes - the projector legitimately emits some edges
(subsystem->sensor) before the sensor node is upserted, and each write commits
independently. `neighbors()` filters to existing nodes, exactly as in-memory. A
referential FK would reject the projector's own ordering and change behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_knowledge_graph"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge.kg_node (
            node_id    TEXT        PRIMARY KEY,
            node_type  TEXT        NOT NULL,
            properties JSONB       NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_kg_node_type ON knowledge.kg_node (node_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge.kg_edge (
            src        TEXT        NOT NULL,
            dst        TEXT        NOT NULL,
            edge_type  TEXT        NOT NULL,
            properties JSONB       NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (src, dst, edge_type)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_kg_edge_type ON knowledge.kg_edge (edge_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kg_edge_src ON knowledge.kg_edge (src)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge.kg_edge")
    op.execute("DROP TABLE IF EXISTS knowledge.kg_node")
