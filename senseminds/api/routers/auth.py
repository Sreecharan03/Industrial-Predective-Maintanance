"""Authentication endpoints: token issuance + current-principal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from senseminds.api.deps import AppState, Principal, current_user, state
from senseminds.api.security import create_access_token, verify_password
from senseminds.infrastructure.repositories import UnitOfWork

router = APIRouter(prefix="/auth", tags=["auth"])


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Me(BaseModel):
    username: str
    roles: list[str]


@router.post("/token", response_model=Token)
def token(
    form: OAuth2PasswordRequestForm = Depends(), app: AppState = Depends(state)
) -> Token:
    with UnitOfWork(app.db) as uow:
        user = uow.users.get(form.username)
    ok = (user is not None and user.is_active
          and verify_password(form.password, user.hashed_password))
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect username or password")
    access = create_access_token(
        user.username, user.roles, app.settings.jwt_secret,
        app.settings.jwt_algorithm, app.settings.access_token_ttl_minutes,
    )
    return Token(access_token=access)


@router.get("/me", response_model=Me)
def me(principal: Principal = Depends(current_user)) -> Me:
    return Me(username=principal.username, roles=list(principal.roles))
