"""Database infrastructure (ADR-019).

SQLAlchemy engine + per-store session seam. Persistence lives only in the
infrastructure ring; nothing here leaks into domain/engines. The three logical
stores (sensor_history / knowledge / application) each resolve their own engine
so they can later point at independent databases without any code change
(ADR-019 R4). Synchronous engines: the analytics data-path is synchronous pandas
code, so a sync session is the correct fit (an async surface can arrive with the
API later).
"""

from senseminds.infrastructure.db.engine import Database, build_database
from senseminds.infrastructure.db.schema import (
    APPLICATION,
    KNOWLEDGE,
    SENSOR_HISTORY,
    StoreSchema,
)

__all__ = [
    "APPLICATION",
    "KNOWLEDGE",
    "SENSOR_HISTORY",
    "Database",
    "StoreSchema",
    "build_database",
]
