"""Knowledge-graph projector (ADR-014).

Deterministic, idempotent projection of catalog structure and Findings into the
graph. Projecting the same inputs any number of times, in any order, yields an
identical graph state (R1, mandatory): a `FindingCondition` node absorbs the SET
of distinct finding_ids it has seen, so `occurrences = |set|`, and
first_seen/last_seen/latest are folded via order-independent min/max - re-
projecting an already-absorbed finding is a no-op. Nodes key by id, edges by
(src, dst, type), so upserts dedup by construction.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from senseminds.catalog import thresholds_for
from senseminds.domain.entities import Asset
from senseminds.domain.enums import ThresholdStatus
from senseminds.findings import Finding, FindingScope
from senseminds.knowledge_graph.models import Edge, EdgeType, Node, NodeType
from senseminds.knowledge_graph.repository import KnowledgeGraphRepository


# --- deterministic node ids ---
def equipment_id(unit: str) -> str:
    return f"equipment:{unit}"


def subsystem_id(unit: str, key: str) -> str:
    return f"subsystem:{unit}:{key}"


def sensor_id(unit: str, key: str) -> str:
    return f"sensor:{unit}:{key}"


def threshold_id(unit: str, key: str) -> str:
    return f"threshold:{unit}:{key}"


def condition_id(identity_key: str) -> str:
    return f"condition:{identity_key}"


def artifact_ref_id(artifact_id: str) -> str:
    return f"artifact:{artifact_id}"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _min_iso(existing: object, dt: datetime | None) -> str | None:
    cand = _iso(dt)
    if existing is None:
        return cand
    if cand is None:
        return existing  # type: ignore[return-value]
    return min(str(existing), cand)


def _max_iso(existing: object, dt: datetime | None) -> str | None:
    cand = _iso(dt)
    if existing is None:
        return cand
    if cand is None:
        return existing  # type: ignore[return-value]
    return max(str(existing), cand)


def _newer(cand_end: str | None, cand_fid: str, cur_end: object, cur_fid: object) -> bool:
    """Order-independent 'is (end, fid) the latest so far' - None end sorts first."""
    return (cand_end or "", cand_fid) > (str(cur_end or ""), str(cur_fid or ""))


class KnowledgeGraphProjector:
    """Fold catalog structure + Findings into a knowledge graph, idempotently."""

    def __init__(self, repo: KnowledgeGraphRepository) -> None:
        self._repo = repo

    # ---------------------------- structure ----------------------------
    def seed_catalog(self, asset: Asset, thresholds: Mapping | None = None) -> None:
        unit = asset.key
        self._repo.upsert_node(
            Node(
                node_id=equipment_id(unit),
                node_type=NodeType.EQUIPMENT,
                properties={
                    "key": unit,
                    "equipment_class": asset.equipment_class.value,
                    "display_name": asset.display_name,
                },
            )
        )
        for sub in asset.subsystems:
            sid = subsystem_id(unit, sub.key)
            self._repo.upsert_node(
                Node(
                    node_id=sid,
                    node_type=NodeType.SUBSYSTEM,
                    properties={"key": sub.key, "name": sub.display_name, "equipment_key": unit},
                )
            )
            self._repo.upsert_edge(
                Edge(src=equipment_id(unit), dst=sid, edge_type=EdgeType.HAS_SUBSYSTEM)
            )
            for skey in sub.sensor_keys:
                self._repo.upsert_edge(
                    Edge(src=sid, dst=sensor_id(unit, skey), edge_type=EdgeType.HAS_SENSOR)
                )

        th = thresholds if thresholds is not None else thresholds_for(unit, asset)
        for sensor in asset.sensors:
            self._repo.upsert_node(
                Node(
                    node_id=sensor_id(unit, sensor.key),
                    node_type=NodeType.SENSOR,
                    properties={
                        "key": sensor.key,
                        "sensor_type": sensor.sensor_type.value,
                        "unit": sensor.unit.symbol,
                        "equipment_key": unit,
                    },
                )
            )
            td = th.get(sensor.key)
            if td is not None and td.status is ThresholdStatus.AVAILABLE:
                tid = threshold_id(unit, sensor.key)
                self._repo.upsert_node(
                    Node(
                        node_id=tid,
                        node_type=NodeType.THRESHOLD_DEFINITION,
                        properties={
                            "sensor_key": sensor.key,
                            "operating_min": td.minimum,
                            "operating_max": td.maximum,
                            "status": td.status.value,
                        },
                    )
                )
                self._repo.upsert_edge(
                    Edge(
                        src=sensor_id(unit, sensor.key),
                        dst=tid,
                        edge_type=EdgeType.GOVERNED_BY,
                    )
                )

    # ---------------------------- findings ----------------------------
    def project_findings(self, findings: Iterable[Finding]) -> None:
        for f in findings:
            self._project_one(f)

    def _project_one(self, f: Finding) -> None:
        cid = condition_id(f.identity_key)
        existing = self._repo.get_node(cid)
        self._repo.upsert_node(self._fold_condition(cid, existing, f))
        self._repo.upsert_edge(
            Edge(src=cid, dst=self._target_id(f), edge_type=EdgeType.OBSERVED_ON)
        )
        for trigger_identity in f.triggered_by:  # reasoning chain (ADR-015 R1)
            self._repo.upsert_edge(
                Edge(
                    src=cid,
                    dst=condition_id(trigger_identity),
                    edge_type=EdgeType.TRIGGERED_BY,
                )
            )
        for ev in f.evidence:
            self._project_evidence(cid, f, ev)

    def _fold_condition(self, cid: str, existing: Node | None, f: Finding) -> Node:
        props = dict(existing.properties) if existing is not None else {}
        observed = set(props.get("observed_finding_ids", []))  # type: ignore[arg-type]
        observed.add(f.finding_id)
        end_iso = _iso(f.observed_window.end)
        is_latest = _newer(
            end_iso, f.finding_id, props.get("latest_window_end"), props.get("latest_finding_id")
        )
        return Node(
            node_id=cid,
            node_type=NodeType.FINDING_CONDITION,
            properties={
                "identity_key": f.identity_key,
                "finding_type": f.finding_type.value,
                "category": f.category.value,
                "origin": f.origin.value,
                "scope": f.scope.value,
                "target_key": f.target_key,
                "equipment_key": f.equipment_key,
                "subsystem_key": f.subsystem_key,
                "first_seen": _min_iso(props.get("first_seen"), f.observed_window.start),
                "last_seen": _max_iso(props.get("last_seen"), f.observed_window.end),
                "occurrences": len(observed),
                "observed_finding_ids": sorted(observed),
                "latest_finding_id": f.finding_id if is_latest else props.get("latest_finding_id"),
                "latest_severity": f.severity.value if is_latest else props.get("latest_severity"),
                "latest_window_end": end_iso if is_latest else props.get("latest_window_end"),
                "status": "active",
            },
        )

    def _project_evidence(self, cid: str, f: Finding, ev: object) -> None:
        artifact_id = ev.artifact_id  # type: ignore[attr-defined]
        aref = artifact_ref_id(artifact_id)
        self._repo.upsert_node(
            Node(
                node_id=aref,
                node_type=NodeType.ARTIFACT_REF,
                properties={"artifact_id": artifact_id},
            )
        )
        key = (cid, aref, EdgeType.HAS_EVIDENCE.value)
        by_key = {e.key: e for e in self._repo.edges(edge_type=EdgeType.HAS_EVIDENCE, src=cid)}
        existing = by_key.get(key)
        end_iso = _iso(f.observed_window.end)
        cur_end = existing.properties.get("from_window_end") if existing else None
        cur_fid = existing.properties.get("from_finding_id") if existing else None
        if existing is None or _newer(end_iso, f.finding_id, cur_end, cur_fid):
            self._repo.upsert_edge(
                Edge(
                    src=cid,
                    dst=aref,
                    edge_type=EdgeType.HAS_EVIDENCE,
                    properties={
                        "observed_value": ev.observed_value,  # type: ignore[attr-defined]
                        "description": ev.description,  # type: ignore[attr-defined]
                        "from_finding_id": f.finding_id,
                        "from_window_end": end_iso,
                    },
                )
            )

    @staticmethod
    def _target_id(f: Finding) -> str:
        if f.scope is FindingScope.SENSOR:
            return sensor_id(f.equipment_key, f.target_key)
        if f.scope is FindingScope.SUBSYSTEM:
            return subsystem_id(f.equipment_key, f.target_key)
        return equipment_id(f.equipment_key)
