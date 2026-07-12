"""Identity seed (ADR-018 serving).

Ensures the standard roles and a bootstrap admin user exist so a fresh
deployment is immediately usable. Idempotent: existing users/roles are left
intact (the admin password is only set when the admin is first created).
"""

from __future__ import annotations

from datetime import UTC, datetime

from senseminds.api.security import hash_password
from senseminds.config import Settings
from senseminds.infrastructure.db import Database
from senseminds.infrastructure.repositories import UnitOfWork
from senseminds.repositories.models import Role, User

_ROLES = {
    "operator": "Plant operator",
    "maintenance_engineer": "Maintenance engineer",
    "reliability_engineer": "Reliability engineer",
    "plant_manager": "Plant manager",
    "executive": "Executive",
    "admin": "Administrator",
}


def seed_identity(db: Database, settings: Settings) -> None:
    with UnitOfWork(db) as uow:
        for name, description in _ROLES.items():
            uow.users.save_role(Role(name=name, description=description))
        if uow.users.get(settings.default_admin_username) is None:
            uow.users.save(User(
                username=settings.default_admin_username,
                hashed_password=hash_password(settings.default_admin_password),
                roles=("admin",), created_at=datetime.now(tz=UTC),
            ))
