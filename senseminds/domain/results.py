"""Typed engine-result base.

Every deterministic engine (statistics, threshold, operating-state, ...)
returns a subclass of `EngineResult`: a payload plus `Provenance`. These typed
results - not another engine's internal state - are what downstream layers
consume, and what the artifact store persists (ADR-004, HLD 4).
"""

from __future__ import annotations

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.value_objects import Provenance


class EngineResult(FrozenModel):
    """Immutable base for all engine outputs. Subclasses add payload fields."""

    artifact_id: str = Field(min_length=1, description="Stable id used to reference this result.")
    provenance: Provenance

    @property
    def result_type(self) -> str:
        """The concrete result class name - used as the artifact kind on disk."""
        return type(self).__name__
