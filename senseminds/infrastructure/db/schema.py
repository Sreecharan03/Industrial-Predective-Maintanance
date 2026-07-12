"""Logical store schemas (ADR-019 §1.1, R4).

Three independent schemas in one Postgres instance today. They carry **no
cross-schema foreign keys** (links are soft references by stable text key), so
each could become its own database later without touching domain/application
code.
"""

from __future__ import annotations

from enum import StrEnum


class StoreSchema(StrEnum):
    """A logical persistence store, mapped to a Postgres schema name."""

    SENSOR_HISTORY = "sensor_history"
    KNOWLEDGE = "knowledge"
    APPLICATION = "application"


SENSOR_HISTORY = StoreSchema.SENSOR_HISTORY
KNOWLEDGE = StoreSchema.KNOWLEDGE
APPLICATION = StoreSchema.APPLICATION
