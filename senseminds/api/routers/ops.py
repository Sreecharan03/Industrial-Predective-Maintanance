"""Operational endpoints: liveness, readiness, metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text

from senseminds import __version__
from senseminds.api.deps import AppState, state
from senseminds.infrastructure.db import APPLICATION, KNOWLEDGE

router = APIRouter(tags=["ops"])


class Health(BaseModel):
    status: str
    version: str
    environment: str


@router.get("/health", response_model=Health)
def health(app: AppState = Depends(state)) -> Health:
    return Health(status="ok", version=__version__, environment=app.settings.environment)


@router.get("/ready")
def ready(app: AppState = Depends(state)) -> Response:
    try:
        with app.db.session(APPLICATION) as session:
            session.execute(text("SELECT 1"))
        return Response(status_code=200, content="ready")
    except Exception:
        return Response(status_code=503, content="database unavailable")


@router.get("/metrics")
def metrics(app: AppState = Depends(state)) -> Response:
    lines = ["# platform metrics", "senseminds_up 1"]
    try:
        with app.db.session(APPLICATION) as s:
            findings = s.execute(text("SELECT count(*) FROM application.finding")).scalar_one()
            runs = s.execute(text("SELECT count(*) FROM application.engine_run")).scalar_one()
        with app.db.session(KNOWLEDGE) as s:
            nodes = s.execute(text("SELECT count(*) FROM knowledge.kg_node")).scalar_one()
        lines += [
            f"senseminds_findings_total {findings}",
            f"senseminds_engine_runs_total {runs}",
            f"senseminds_kg_nodes_total {nodes}",
        ]
    except Exception:
        lines.append("senseminds_db_reachable 0")
    return Response("\n".join(lines) + "\n", media_type="text/plain")
