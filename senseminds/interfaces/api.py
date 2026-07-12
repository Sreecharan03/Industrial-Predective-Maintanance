"""FastAPI application factory.

Thin interface layer (ADR dependency rule): it wires configuration, logging,
and (later) use-cases into HTTP routes and nothing more. `create_app()` is a
factory so tests can build an isolated app instance. At M0 the only route is a
liveness/readiness health check; capability routes arrive with their
use-cases in later milestones.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from senseminds import __version__
from senseminds.config import Settings, get_settings
from senseminds.infrastructure.logging import configure_logging, get_logger


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__, environment=settings.environment)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log.info("app_startup", extra={"version": __version__})
        yield
        log.info("app_shutdown")

    app = FastAPI(
        title="SenseMinds 360",
        version=__version__,
        summary="Industrial Intelligence Platform",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok", version=__version__, environment=settings.environment
        )

    return app
