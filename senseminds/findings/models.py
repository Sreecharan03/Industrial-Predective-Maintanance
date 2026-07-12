"""The immutable Finding contract (ADR-013 §4).

A Finding is a validated engineering *claim* - an observation, never a
measurement. It is immutable and carries no workflow state and no priority
(those live outside it, ADR-013 §10). Every Finding must reference at least one
piece of `Evidence`; construction without evidence or provenance is rejected.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings.enums import (
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
)


class ObservedWindow(FrozenModel):
    """The history window a finding pertains to (metadata, not identity)."""

    start: datetime | None = None
    end: datetime | None = None


class Finding(FrozenModel):
    """An immutable, deterministic engineering claim about an asset."""

    finding_id: str = Field(min_length=1, description="hash(identity_key, input_hash).")
    identity_key: str = Field(min_length=1, description="hash(type, scope, target) - stable.")
    finding_type: FindingType
    category: FindingCategory
    scope: FindingScope
    origin: FindingOrigin
    summary: str = Field(min_length=1, description="One-line 'what happened'.")
    detail: str = Field(description="The engineering rationale ('why').")
    target_key: str = Field(min_length=1, description="The scoped entity (sensor/subsystem/...).")
    equipment_key: str = Field(min_length=1)
    subsystem_key: str | None = None
    severity: Severity
    confidence: Confidence
    evidence: tuple[Evidence, ...] = Field(min_length=1, description="Deterministic backing (>=1).")
    source_engine: str = Field(min_length=1, description="Producing engine/result.")
    observed_window: ObservedWindow
    provenance: Provenance
    supersedes: str | None = Field(default=None, description="finding_id of the prior observation.")
    triggered_by: tuple[str, ...] = Field(
        default_factory=tuple,
        description="identity_keys of the findings that triggered this rule (DIAGNOSED only) "
        "- the persistent, auditable reasoning chain (ADR-015 R1).",
    )
