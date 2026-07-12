"""Health engine.

Deterministic hierarchical health: sensor -> subsystem -> equipment. Consumes
the AnalysisContext (reliability + threshold + catalog subsystems) - it does
NOT evaluate thresholds itself (it reads the Threshold engine's verdict) and
is not ML-derived (ADR-008). Each sensor's health reflects its threshold state
where a threshold exists, else its data reliability; the score's *confidence*
comes from the Sensor Trust engine, so an untrustworthy sensor yields a health
score you are told not to over-trust. Rollups are confidence-weighted means;
severity always propagates the worst child.
"""

from __future__ import annotations

from senseminds.application.context import AnalysisContext
from senseminds.domain.entities import HealthScore
from senseminds.domain.enums import Severity, ThresholdStatus
from senseminds.domain.value_objects import Confidence, Evidence
from senseminds.engines.base import BaseEngine
from senseminds.engines.health.models import HealthResult
from senseminds.engines.threshold.models import ThresholdState

# Operating health + severity implied by a sensor's current threshold state.
_STATE_HEALTH: dict[ThresholdState, tuple[float, Severity]] = {
    ThresholdState.WITHIN_RANGE: (100.0, Severity.OK),
    ThresholdState.OUTSIDE_OPERATING: (60.0, Severity.WARNING),
    ThresholdState.CRITICAL: (30.0, Severity.CRITICAL),
    ThresholdState.TRIP: (0.0, Severity.CRITICAL),
}


def _severity_from_score(score: float) -> Severity:
    if score >= 80:
        return Severity.OK
    if score >= 50:
        return Severity.WARNING
    return Severity.CRITICAL


def _worst(severities: list[Severity]) -> Severity:
    return max(severities, key=lambda s: s.rank) if severities else Severity.OK


class HealthEngine(BaseEngine):
    """Compute a unit's hierarchical health from upstream engine results."""

    name = "health"
    version = "0.1.0"

    def compute(self, context: AnalysisContext) -> HealthResult:
        context.require("reliability", "threshold")
        unit = context.unit
        asset = context.series.asset

        sensors = tuple(self._sensor_health(context, key) for key in _sensor_keys(context))
        by_key = {s.target_key: s for s in sensors}

        subsystems = tuple(
            self._rollup(
                "subsystem",
                sub.key,
                [by_key[k] for k in sub.sensor_keys if k in by_key],
                context.reliability.artifact_id,
            )
            for sub in asset.subsystems
        )
        equipment = self._rollup(
            "equipment", unit, list(subsystems), context.reliability.artifact_id
        )
        self.log.info("health_scored", extra={"unit": unit, "equipment_score": equipment.score})
        return HealthResult(
            artifact_id=f"{unit}__health",
            provenance=self.provenance(unit, input_hash=context.reliability.provenance.input_hash),
            unit=unit,
            equipment=equipment,
            subsystems=subsystems,
            sensors=sensors,
        )

    @staticmethod
    def _sensor_health(context: AnalysisContext, key: str) -> HealthScore:
        rel = context.reliability.sensor(key)
        thr = context.threshold.sensor(key)
        trust = rel.sensor_confidence if rel else Confidence(value=0.0, rationale="no reliability")

        thresholded = (
            thr is not None
            and thr.status is ThresholdStatus.AVAILABLE
            and thr.current_state in _STATE_HEALTH
        )
        if thresholded:
            score, severity = _STATE_HEALTH[thr.current_state]
            basis = f"current threshold state = {thr.current_state.value}"
            ev_desc = thr.evidence.interpretation
            observed = thr.latest_value
        else:
            score = round(trust.value * 100, 1)
            severity = _severity_from_score(score)
            basis = "data reliability (no representative threshold)"
            ev_desc = f"reliability score {rel.reliability_score if rel else 0}"
            observed = None

        evidence = (
            Evidence(
                artifact_id=context.reliability.artifact_id,
                description=f"sensor trust {trust.value}",
                observed_value=rel.reliability_score if rel else None,
            ),
            Evidence(
                artifact_id=context.threshold.artifact_id,
                description=ev_desc,
                observed_value=observed,
            ),
        )
        return HealthScore(
            scope="sensor",
            target_key=key,
            score=score,
            severity=severity,
            confidence=trust,
            contributing_factors=(f"reliability {rel.reliability_score if rel else 0}", basis),
            evidence=evidence,
        )

    @staticmethod
    def _rollup(
        scope: str, key: str, children: list[HealthScore], evidence_artifact: str
    ) -> HealthScore:
        if not children:
            return HealthScore(
                scope=scope,
                target_key=key,
                score=100.0,
                severity=Severity.OK,
                confidence=Confidence(value=0.0, rationale="no child scores to aggregate"),
                contributing_factors=("no scored children",),
            )
        weights = [c.confidence.value if c.confidence else 1.0 for c in children]
        wsum = sum(weights) or float(len(children))
        score = round(
            sum(c.score * w for c, w in zip(children, weights, strict=True)) / wsum, 1
        )
        severity = _worst([c.severity for c in children])
        conf_value = round(sum(weights) / len(children), 4)
        worst_children = sorted(children, key=lambda c: c.score)[:3]
        factors = tuple(
            f"{c.target_key}: {c.score} ({c.severity.value})" for c in worst_children
        )
        evidence = (
            Evidence(
                artifact_id=evidence_artifact,
                description=f"{scope} rolled up from {len(children)} children "
                f"(confidence-weighted mean; worst severity propagated)",
                observed_value=score,
            ),
        )
        return HealthScore(
            scope=scope,
            target_key=key,
            score=score,
            severity=severity,
            confidence=Confidence(
                value=conf_value, rationale=f"mean reliability of {len(children)} children"
            ),
            contributing_factors=factors,
            evidence=evidence,
        )


def _sensor_keys(context: AnalysisContext) -> tuple[str, ...]:
    return context.series.manifest.sensor_keys
