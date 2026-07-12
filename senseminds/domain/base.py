"""Shared model bases.

`FrozenModel` is the single immutable, extra-forbidding Pydantic base used by
every value object, engine sub-model, and engine result across the platform -
so immutability and strict field validation are defined once, not redefined per
module (ADR-011 finding 2.3).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Immutable, equality-by-value, no-extra-fields Pydantic base."""

    model_config = ConfigDict(frozen=True, extra="forbid")
