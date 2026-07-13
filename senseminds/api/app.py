"""FastAPI application (ADR-018 serving).

The production HTTP surface over the frozen platform. Builds the composition root
once at startup, seeds identity, and mounts the versioned routers. Routes read
persisted, grounded state and trigger the atomic analysis use case; they never
touch engines or telemetry directly.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from senseminds import __version__
from senseminds.api.deps import build_state
from senseminds.api.routers import analysis, assets, auth, ingest, llm, ops, telemetry
from senseminds.api.seed import seed_identity
from senseminds.config import Settings, get_settings
from senseminds.infrastructure.logging import configure_logging, get_logger

_API_V1 = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__, environment=settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.app_state = build_state(settings)
        seed_identity(app.state.app_state.db, settings)
        log.info("api_startup", extra={"version": __version__})
        try:
            yield
        finally:
            app.state.app_state.close()
            log.info("api_shutdown")

    app = FastAPI(
        title="SenseMinds 360",
        version=__version__,
        summary="Industrial Intelligence Platform",
        lifespan=lifespan,
    )
    @app.middleware("http")
    async def _log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        log.info("http_request", extra={
            "request_id": request_id, "method": request.method,
            "path": request.url.path, "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        })
        return response

    app.include_router(ops.router)  # health/ready/metrics at root
    for r in (auth.router, assets.router, telemetry.router, analysis.router,
              ingest.router, llm.router):
        app.include_router(r, prefix=_API_V1)
    return app
