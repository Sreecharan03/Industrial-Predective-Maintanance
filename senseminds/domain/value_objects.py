"""Domain value objects.

Immutable, equality-by-value concepts with no identity of their own. Frozen so
they can be shared freely and used as dict keys / set members. No I/O, no
pandas - pure domain.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EngineeringUnit(_Frozen):
    """A physical engineering unit, with a flag for whether it was inferred.

    The Phase-1 sensor mapping distinguished units printed in the source header
    from units inferred from context (e.g. ``kg/cm2 (assumed)``); that
    distinction is preserved here so downstream reasoning can treat an assumed
    unit with appropriate caution.
    """

    symbol: str = Field(min_length=1, description="e.g. 'kg/cm2', 'C', 'A', '%', 'Nm3/hr'.")
    assumed: bool = Field(default=False, description="True if inferred rather than source-stated.")


class Confidence(_Frozen):
    """A bounded [0, 1] confidence with a required human-readable rationale.

    A confidence without a reason is not permitted - every graded assertion in
    the platform must explain itself (the "explainable" tenet, enforced by type).
    """

    value: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class Provenance(_Frozen):
    """Where a computed artifact came from - the spine of traceability.

    Every engine result carries provenance so any downstream finding can be
    traced to the exact code version and input that produced it (ADR-004).
    """

    engine: str = Field(min_length=1, description="Producing engine name, e.g. 'operating_state'.")
    engine_version: str = Field(min_length=1, description="Semver/string version of that engine.")
    source_unit: str = Field(min_length=1, description="Asset/unit the input belonged to.")
    input_hash: str = Field(min_length=1, description="Stable hash of the exact input consumed.")
    produced_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @model_validator(mode="after")
    def _tz_aware(self) -> Provenance:
        if self.produced_at.tzinfo is None:
            raise ValueError("produced_at must be timezone-aware")
        return self


class Evidence(_Frozen):
    """A pointer from a Finding to the structured artifact that justifies it.

    Findings never assert facts inline; they reference Evidence, and Evidence
    references an artifact id + the specific field/observation. This is the
    mechanism that makes "every recommendation references evidence" true by
    construction (HLD 4).
    """

    artifact_id: str = Field(min_length=1, description="ID of the source engine result.")
    description: str = Field(min_length=1, description="What this evidence shows, in one line.")
    observed_value: float | str | None = Field(
        default=None, description="The specific value that mattered, if scalar."
    )
