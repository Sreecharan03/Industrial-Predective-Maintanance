"""REST API (ADR-018 serving) - auth, read surface, analyze, grounded LLM query.

Uses the deterministic stub model (no GROQ key) so it runs offline. Integration
test - skipped unless a Postgres/TimescaleDB and processed CSVs are present.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from senseminds.config import Settings

_PROCESSED = Path(__file__).resolve().parents[2] / "Datasets" / "processed"


def _db_url() -> str:
    return os.environ.get("SENSEMINDS_DATABASE_URL") or Settings().database_url


def _db_available(url: str) -> bool:
    try:
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists() or not _db_available(_db_url()),
    reason="TimescaleDB or processed CSV not available",
)


@pytest.fixture(scope="module")
def client():  # noqa: ANN201
    from senseminds.api import create_app
    from senseminds.application.bootstrap import bootstrap_units
    from senseminds.infrastructure.db import build_database
    from senseminds.infrastructure.db.migrate import upgrade

    settings = Settings(database_url=_db_url(), groq_api_key="")  # stub model
    upgrade(_db_url())
    db = build_database(settings)
    bootstrap_units(db, _PROCESSED, units=["SC-126"])  # ensure readings exist
    # fresh application/knowledge state so the first analyze is a real run
    from senseminds.infrastructure.db import APPLICATION, KNOWLEDGE
    with db.session(APPLICATION) as s:
        s.execute(sqlalchemy.text(
            "TRUNCATE application.finding, application.report, application.engine_run, "
            "application.asset"))
    with db.session(KNOWLEDGE) as s:
        s.execute(sqlalchemy.text("TRUNCATE knowledge.kg_edge, knowledge.kg_node"))
    db.dispose()

    with TestClient(create_app(settings)) as c:
        yield c


def _auth(client: TestClient) -> dict:
    resp = client.post("/api/v1/auth/token", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_health_and_ready_are_open(client) -> None:  # noqa: ANN001
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    assert "senseminds_up 1" in client.get("/metrics").text


def test_protected_routes_require_auth(client) -> None:  # noqa: ANN001
    assert client.get("/api/v1/assets").status_code == 401
    assert client.post("/api/v1/llm/query", json={"unit": "SC-126"}).status_code == 401


def test_login_and_me(client) -> None:  # noqa: ANN001
    headers = _auth(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["username"] == "admin" and "admin" in me["roles"]


def test_analyze_then_read_findings_and_query(client) -> None:  # noqa: ANN001
    headers = _auth(client)

    analyze = client.post("/api/v1/analyze", json={"unit": "SC-126"}, headers=headers)
    assert analyze.status_code == 200, analyze.text
    assert analyze.json()["finding_count"] > 0

    assets = client.get("/api/v1/assets", headers=headers).json()
    assert any(a["unit"] == "SC-126" for a in assets)

    findings = client.get("/api/v1/assets/SC-126/findings", headers=headers).json()
    assert findings and all("finding_id" in f for f in findings)

    diagnoses = client.get("/api/v1/assets/SC-126/diagnoses", headers=headers).json()
    assert all(f["origin"] == "diagnosed" for f in diagnoses)

    graph = client.get("/api/v1/assets/SC-126/graph", headers=headers).json()
    assert any(n["id"] == "equipment:SC-126" for n in graph["nodes"])

    reports = client.get("/api/v1/assets/SC-126/reports", headers=headers).json()
    assert reports  # the analysis produced a daily report

    answer = client.post("/api/v1/llm/query",
                         json={"unit": "SC-126", "question": "How is it?",
                               "persona": "operator"}, headers=headers).json()
    assert answer["claims"] and answer["citations"]  # grounded + cited
    valid_ids = {f["finding_id"] for f in findings}
    for claim in answer["claims"]:
        assert set(claim["citations"]) <= valid_ids  # every citation is a real finding


def test_replayed_analysis_is_idempotent(client) -> None:  # noqa: ANN001
    headers = _auth(client)
    client.post("/api/v1/analyze", json={"unit": "SC-126"}, headers=headers)
    second = client.post("/api/v1/analyze", json={"unit": "SC-126"}, headers=headers).json()
    assert second["replayed"] is True  # same input hash -> no-op
