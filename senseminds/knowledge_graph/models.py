"""Knowledge-graph node and edge models (ADR-014).

Typed, immutable graph primitives. Nodes carry a JSON-serialisable property map;
the graph stores *knowledge* (structure + finding-conditions + curated
knowledge), never telemetry. Updates replace a node/edge wholesale (upsert),
keeping every stored object an immutable snapshot.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from senseminds.domain.base import FrozenModel


class NodeType(StrEnum):
    EQUIPMENT = "equipment"
    SUBSYSTEM = "subsystem"
    SENSOR = "sensor"
    THRESHOLD_DEFINITION = "threshold_definition"
    FINDING_CONDITION = "finding_condition"
    ARTIFACT_REF = "artifact_ref"
    # Pattern Learning (Phase B) - hypotheses, clearly separable from facts.
    DISCOVERED_PATTERN = "discovered_pattern"
    LEARNED_MODEL = "learned_model"
    # Future (ADR-014 §10): FAULT_MECHANISM, FAILURE_MODE, ENGINEERING_RULE,
    # MAINTENANCE_ACTION - not created in this milestone.


class EdgeType(StrEnum):
    HAS_SUBSYSTEM = "has_subsystem"
    HAS_SENSOR = "has_sensor"
    GOVERNED_BY = "governed_by"
    OBSERVED_ON = "observed_on"
    HAS_EVIDENCE = "has_evidence"
    TRIGGERED_BY = "triggered_by"  # DIAGNOSED condition -> the conditions that fired it
    # Pattern Learning (Phase B) - all carry confidence + status=hypothesis.
    SUGGESTS = "suggests"  # LEARNED finding -> discovered pattern
    DISCOVERED_BY = "discovered_by"  # pattern -> learned model
    PRECEDES = "precedes"  # learned temporal/causal sequence (hypothesis)


class Node(FrozenModel):
    """A graph node: stable id + type + JSON-serialisable properties."""

    node_id: str = Field(min_length=1)
    node_type: NodeType
    properties: dict[str, object] = Field(default_factory=dict)


class Edge(FrozenModel):
    """A directed, typed edge. Identity = (src, dst, edge_type)."""

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    edge_type: EdgeType
    properties: dict[str, object] = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.src, self.dst, self.edge_type.value)
