"""API composition + dependencies (ADR-018 serving).

Wires the frozen platform (Database, artifact store, LLM service, analysis use
case) once at startup and injects it into routes. Also provides authentication /
role dependencies. Routes depend only on these - never on concrete stores.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from senseminds.api.security import decode_access_token
from senseminds.application.analysis_use_case import AnalysisUseCase
from senseminds.config import Settings
from senseminds.infrastructure.artifact_store.local import LocalArtifactStore
from senseminds.infrastructure.db import Database, build_database
from senseminds.ingestion import DbTimeSeriesSource
from senseminds.llm import EvidenceRetriever, LlmQueryService, build_language_model

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


@dataclass
class AppState:
    settings: Settings
    db: Database
    analysis: AnalysisUseCase
    llm: LlmQueryService

    def close(self) -> None:
        self.db.dispose()


def build_state(settings: Settings) -> AppState:
    db = build_database(settings)
    store = LocalArtifactStore(settings.artifact_root)
    analysis = AnalysisUseCase(db, store, DbTimeSeriesSource(db))
    llm = LlmQueryService(EvidenceRetriever(db), build_language_model(settings))
    return AppState(settings=settings, db=db, analysis=analysis, llm=llm)


def state(request: Request) -> AppState:
    return request.app.state.app_state


@dataclass(frozen=True)
class Principal:
    username: str
    roles: tuple[str, ...]

    def has_any(self, roles: tuple[str, ...]) -> bool:
        return "admin" in self.roles or any(r in self.roles for r in roles)


def current_user(
    token: str | None = Depends(_oauth2), app: AppState = Depends(state)
) -> Principal:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    claims = decode_access_token(token, app.settings.jwt_secret, app.settings.jwt_algorithm)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return Principal(username=claims.get("sub", ""), roles=tuple(claims.get("roles", [])))


def require_roles(*roles: str):  # noqa: ANN201 - FastAPI dependency factory
    def _dep(principal: Principal = Depends(current_user)) -> Principal:
        if not principal.has_any(roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return principal

    return _dep
