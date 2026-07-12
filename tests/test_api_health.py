"""API: the app boots and reports health."""

from __future__ import annotations

from fastapi.testclient import TestClient
from senseminds import __version__
from senseminds.config.settings import Settings
from senseminds.interfaces import create_app


def test_health_endpoint_reports_ok() -> None:
    app = create_app(Settings(environment="dev"))
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": __version__, "environment": "dev"}
