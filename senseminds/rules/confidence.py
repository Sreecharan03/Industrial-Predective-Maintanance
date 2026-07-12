"""Deterministic diagnosis-confidence composition (ADR-015 R2).

diagnosis_confidence = rule_confidence
                     * evidence_confidence   (mean confidence of the required triggers)
                     * reliability_factor    (min trust of the sensors involved, <= 1)

Clamped to [0, 1]. The rationale records all three inputs so a diagnosis resting
on a drifting/untrustworthy sensor is visibly and explainably discounted.
"""

from __future__ import annotations

from senseminds.domain.value_objects import Confidence


def diagnosis_confidence(
    rule_confidence: float, trigger_confidences: list[float], reliability_factor: float
) -> Confidence:
    evidence_conf = (
        sum(trigger_confidences) / len(trigger_confidences) if trigger_confidences else 1.0
    )
    value = max(0.0, min(1.0, rule_confidence * evidence_conf * reliability_factor))
    return Confidence(
        value=round(value, 4),
        rationale=(
            f"rule {rule_confidence} x evidence {round(evidence_conf, 4)} "
            f"x reliability {round(reliability_factor, 4)}"
        ),
    )
