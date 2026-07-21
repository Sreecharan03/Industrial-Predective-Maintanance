"""Operational endpoints: liveness, readiness, metrics.

These make the deployment operationally supportable without a full observability
stack: /health is process liveness, /ready is database reachability (what a load
balancer and the restart policy watch), and /metrics is a Prometheus-format
scrape covering data volume, database health, and host resources — including
disk headroom on the persistent disk, since a full disk is the most direct
threat to the durability guarantee.
"""

from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text

from senseminds import __version__
from senseminds.api.deps import AppState, state
from senseminds.infrastructure.db import APPLICATION, KNOWLEDGE

router = APIRouter(tags=["ops"])


def _host_gauges(artifact_root: str) -> list[str]:
    """Best-effort host resource gauges from the stdlib (no extra dependency)."""
    out: list[str] = []
    try:
        usage = shutil.disk_usage(artifact_root if os.path.isdir(artifact_root) else "/")
        out += [
            f"senseminds_disk_total_bytes {usage.total}",
            f"senseminds_disk_used_bytes {usage.used}",
            f"senseminds_disk_free_bytes {usage.free}",
            f"senseminds_disk_used_ratio {usage.used / usage.total:.4f}",
        ]
    except Exception:
        pass
    try:
        load1, load5, load15 = os.getloadavg()
        out += [f"senseminds_load1 {load1:.2f}", f"senseminds_load5 {load5:.2f}"]
    except (OSError, AttributeError):
        pass
    try:
        with open("/proc/meminfo") as fh:
            mem = {k.strip(): v for k, v in (ln.split(":", 1) for ln in fh)}
        total_kb = int(mem["MemTotal"].split()[0])
        avail_kb = int(mem["MemAvailable"].split()[0])
        out += [
            f"senseminds_memory_total_bytes {total_kb * 1024}",
            f"senseminds_memory_available_bytes {avail_kb * 1024}",
        ]
    except (OSError, KeyError, ValueError):
        pass
    return out


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
            alerts = s.execute(text("SELECT count(*) FROM application.alert")).scalar_one()
        with app.db.session(KNOWLEDGE) as s:
            nodes = s.execute(text("SELECT count(*) FROM knowledge.kg_node")).scalar_one()
        lines += [
            "senseminds_db_reachable 1",
            f"senseminds_findings_total {findings}",
            f"senseminds_engine_runs_total {runs}",
            f"senseminds_alerts_total {alerts}",
            f"senseminds_kg_nodes_total {nodes}",
        ]
    except Exception:
        lines.append("senseminds_db_reachable 0")

    # Connection-pool health per store — catches pool exhaustion before it
    # becomes request failures.
    for name, schema in (("application", APPLICATION), ("knowledge", KNOWLEDGE)):
        try:
            pool = app.db.engine(schema).pool
            lines.append(f'senseminds_db_pool_checkedout{{store="{name}"}} '
                         f"{pool.checkedout()}")  # type: ignore[attr-defined]
        except Exception:
            pass

    lines += _host_gauges(str(app.settings.artifact_root))
    return Response("\n".join(lines) + "\n", media_type="text/plain")
