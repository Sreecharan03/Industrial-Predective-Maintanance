"""Asset, findings, diagnoses, reports, and knowledge-graph read endpoints.

The dashboard/read surface. Every response is a projection of already-persisted,
grounded state - the API computes nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from senseminds.api.deps import AppState, current_user, state
from senseminds.infrastructure.graph_store import PostgresKnowledgeGraph
from senseminds.infrastructure.repositories import UnitOfWork

router = APIRouter(prefix="/assets", tags=["assets"], dependencies=[Depends(current_user)])


@router.get("")
def list_assets(app: AppState = Depends(state)) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        units = uow.assets.list_units()
        out = []
        for unit in units:
            asset = uow.assets.get(unit)
            out.append({"unit": unit, "equipment_class": asset.equipment_class.value,
                        "display_name": asset.display_name,
                        "sensor_count": len(asset.sensors)})
    return out


@router.get("/{unit}")
def get_asset(unit: str, app: AppState = Depends(state)) -> dict:
    with UnitOfWork(app.db) as uow:
        asset = uow.assets.get(unit)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"asset {unit!r} not analysed yet")
    return asset.model_dump(mode="json")


@router.get("/{unit}/findings")
def get_findings(
    unit: str,
    origin: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    app: AppState = Depends(state),
) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        findings = uow.findings.for_unit(unit)
    result = [
        f for f in findings
        if (origin is None or f.origin.value == origin)
        and (category is None or f.category.value == category)
        and (severity is None or f.severity.value == severity)
    ]
    return [f.model_dump(mode="json") for f in result]


@router.get("/{unit}/diagnoses")
def get_diagnoses(unit: str, app: AppState = Depends(state)) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        findings = uow.findings.for_unit(unit)
    return [f.model_dump(mode="json") for f in findings if f.origin.value == "diagnosed"]


@router.get("/{unit}/reports")
def get_reports(unit: str, app: AppState = Depends(state)) -> list[dict]:
    with UnitOfWork(app.db) as uow:
        reports = uow.reports.for_unit(unit)
    return [r.model_dump(mode="json") for r in reports]


@router.get("/{unit}/graph")
def get_graph(unit: str, app: AppState = Depends(state)) -> dict:
    graph = PostgresKnowledgeGraph(app.db)
    nodes = [
        n for n in graph.nodes()
        if f":{unit}" in n.node_id or n.properties.get("equipment_key") == unit
    ]
    node_ids = {n.node_id for n in nodes}
    edges = [e for e in graph.edges() if e.src in node_ids and e.dst in node_ids]
    return {
        "unit": unit,
        "nodes": [{"id": n.node_id, "type": n.node_type.value, "properties": n.properties}
                  for n in nodes],
        "edges": [{"src": e.src, "dst": e.dst, "type": e.edge_type.value,
                   "properties": e.properties} for e in edges],
    }
