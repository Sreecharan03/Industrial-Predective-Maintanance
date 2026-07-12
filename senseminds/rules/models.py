"""Rule Engine definitions (ADR-015).

Immutable rule *definitions* - no execution state. A rule is a deterministic
implication over finding-conditions: a co-located pattern of required findings
(with optional corroboration and excluded negatives) implies a DIAGNOSED
finding. Definitions are versioned and carry their engineering assumptions and
prior confidence, so every diagnosis is explainable.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.enums import Severity
from senseminds.findings.enums import FindingCategory, FindingScope, FindingType


class RuleKind(StrEnum):
    """What a rule does (function axis)."""

    DIAGNOSTIC = "diagnostic"
    CORRELATION = "correlation"
    CONFIRMATION = "confirmation"
    SUPPRESSION = "suppression"
    ESCALATION = "escalation"
    SAFETY = "safety"
    MAINTENANCE = "maintenance"
    RECOVERY = "recovery"
    VALIDATION = "validation"  # platform-consistency, not equipment (ADR-015 R3)


class RuleScope(StrEnum):
    """Where a rule applies (applicability axis)."""

    PLANT_WIDE = "plant_wide"
    EQUIPMENT_CLASS = "equipment_class"
    ASSET_SPECIFIC = "asset_specific"


class RuleDefinition(FrozenModel):
    """An immutable rule. Matching is co-located at ``match_scope``."""

    rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: RuleKind
    scope: RuleScope
    applies_to: tuple[str, ...] = Field(
        default=("*",), description="Equipment classes / asset keys, or '*' for any."
    )
    description: str = Field(min_length=1)
    engineering_assumptions: tuple[str, ...] = Field(default_factory=tuple)
    priority: int = Field(description="Higher fires/ranks first; safety rules are highest.")

    # antecedent
    match_scope: FindingScope = Field(description="Granularity co-located required findings match.")
    required_finding_types: tuple[FindingType, ...] = Field(min_length=1)
    optional_finding_types: tuple[FindingType, ...] = Field(default_factory=tuple)
    excluded_finding_types: tuple[FindingType, ...] = Field(
        default_factory=tuple, description="Must be ABSENT unit-wide for the rule to fire."
    )

    # consequent
    produced_finding_type: FindingType
    produced_category: FindingCategory
    produced_severity: Severity
    indicates_fault_mechanism: str | None = None
    recommended_actions: tuple[str, ...] = Field(default_factory=tuple)

    rule_confidence: float = Field(ge=0.0, le=1.0, description="Prior confidence in this rule.")
    enabled: bool = True
