"""LLM communication models (ADR-018).

Typed, immutable evidence and grounded-output models. The LLM never sees raw
telemetry - only these curated, already-attributed evidence items - and every
engineering statement it returns must cite one of their ``ref`` ids.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from senseminds.domain.base import FrozenModel


class EvidenceCategory(StrEnum):
    """The epistemic register of an evidence item - kept distinct end to end."""

    FACT = "fact"            # DERIVED findings / deterministic analytics
    DIAGNOSIS = "diagnosis"  # DIAGNOSED findings (rule-derived)
    HYPOTHESIS = "hypothesis"  # LEARNED pattern findings
    FORECAST = "forecast"    # LEARNED forecast findings


class EvidenceItem(FrozenModel):
    """One citable piece of grounded evidence."""

    ref: str = Field(min_length=1, description="Citation id (finding_id / rule_id / artifact).")
    kind: str = Field(min_length=1, description="finding | rule | artifact | forecast | pattern.")
    category: EvidenceCategory
    text: str = Field(min_length=1, description="One-line grounded statement.")
    detail: str = Field(default="", description="Engineering rationale / correct interpretation.")
    severity: str | None = None
    confidence: float | None = None


class EvidenceBundle(FrozenModel):
    """The curated, telemetry-free evidence retrieved for one question."""

    unit: str = Field(min_length=1)
    question: str = Field(default="")
    items: tuple[EvidenceItem, ...] = Field(default_factory=tuple)

    def ids(self) -> set[str]:
        return {item.ref for item in self.items}

    def by_category(self, category: EvidenceCategory) -> tuple[EvidenceItem, ...]:
        return tuple(i for i in self.items if i.category is category)


class GroundedClaim(FrozenModel):
    """A single engineering statement - must carry >=1 citation to survive."""

    text: str = Field(min_length=1)
    category: EvidenceCategory
    citations: tuple[str, ...] = Field(default_factory=tuple)


class GroundedAnswer(FrozenModel):
    """A validated LLM response: only cited claims, distinct confidence registers."""

    unit: str
    persona: str
    answer: str
    claims: tuple[GroundedClaim, ...] = Field(default_factory=tuple)
    insufficient: tuple[str, ...] = Field(
        default_factory=tuple, description="Aspects asked about but not supported by evidence."
    )
    citations: tuple[str, ...] = Field(default_factory=tuple)
