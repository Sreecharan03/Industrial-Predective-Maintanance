"""Curated deterministic rule set.

Small, human-authored engineering rule set. Each rule encodes a failure-signature
or platform-consistency pattern over findings. This is the curated knowledge the
Rule Engine reasons with; ML may later *propose* additions here for human review
(ADR-015 §10), but never write them autonomously.
"""

from __future__ import annotations

from senseminds.domain.enums import Severity
from senseminds.findings.enums import FindingCategory, FindingScope, FindingType
from senseminds.rules.models import RuleDefinition, RuleKind, RuleScope

_REFRIGERATION = "refrigeration_screw_compressor"


DEFAULT_RULES: tuple[RuleDefinition, ...] = (
    # REAL for SC-126: a mis-specified threshold with no protection breach and
    # healthy equipment is a configuration issue, not a fault.
    RuleDefinition(
        rule_id="R-THR-CONFIG",
        version="1.0",
        kind=RuleKind.MAINTENANCE,
        scope=RuleScope.EQUIPMENT_CLASS,
        applies_to=("*",),
        description="Threshold inconsistent with operation - recommend setpoint review",
        engineering_assumptions=(
            "A threshold most readings fall outside, with no protection breach and healthy "
            "equipment, reflects a mis-set operating limit rather than a fault.",
        ),
        priority=20,
        match_scope=FindingScope.SENSOR,
        required_finding_types=(FindingType.THRESHOLD_MISSPECIFIED,),
        excluded_finding_types=(FindingType.THRESHOLD_CRITICAL, FindingType.HEALTH_DEGRADED),
        produced_finding_type=FindingType.THRESHOLD_CONFIG_REVIEW_RECOMMENDED,
        produced_category=FindingCategory.DIAGNOSTIC,
        produced_severity=Severity.INFO,
        recommended_actions=("review_operating_setpoints",),
        rule_confidence=0.9,
    ),
    # ILLUSTRATIVE diagnostic (does not fire on healthy SC-126): condenser fouling.
    RuleDefinition(
        rule_id="R-COND-FOUL",
        version="1.0",
        kind=RuleKind.DIAGNOSTIC,
        scope=RuleScope.EQUIPMENT_CLASS,
        applies_to=(_REFRIGERATION,),
        description="Condenser fouling suspected",
        engineering_assumptions=(
            "Sustained high discharge pressure breach together with condenser-side "
            "degradation is a classic fouling signature.",
        ),
        priority=60,
        match_scope=FindingScope.EQUIPMENT,
        required_finding_types=(
            FindingType.THRESHOLD_CRITICAL,
            FindingType.HEALTH_DEGRADED,
        ),
        optional_finding_types=(FindingType.RELIABILITY_DRIFT,),
        produced_finding_type=FindingType.CONDENSER_FOULING_SUSPECTED,
        produced_category=FindingCategory.DIAGNOSTIC,
        produced_severity=Severity.WARNING,
        indicates_fault_mechanism="condenser_fouling",
        recommended_actions=("clean_condenser", "inspect_cooling_water"),
        rule_confidence=0.7,
    ),
    # VALIDATION: a CRITICAL alarm resting on an untrustworthy sensor is a
    # platform-consistency problem, not (yet) an equipment diagnosis.
    RuleDefinition(
        rule_id="R-VALID-CRIT-UNTRUST",
        version="1.0",
        kind=RuleKind.VALIDATION,
        scope=RuleScope.PLANT_WIDE,
        applies_to=("*",),
        description="Critical threshold state on an untrustworthy sensor - verify sensor",
        engineering_assumptions=(
            "A critical alarm from a sensor flagged untrustworthy must be sensor-verified "
            "before it is acted on as a real equipment condition.",
        ),
        priority=90,  # safety/integrity - highest
        match_scope=FindingScope.SENSOR,
        required_finding_types=(
            FindingType.THRESHOLD_CRITICAL,
            FindingType.SENSOR_UNTRUSTWORTHY,
        ),
        produced_finding_type=FindingType.CRITICAL_ON_UNTRUSTWORTHY_SENSOR,
        produced_category=FindingCategory.VALIDATION,
        produced_severity=Severity.WARNING,
        recommended_actions=("verify_sensor_calibration",),
        rule_confidence=0.95,
    ),
)
