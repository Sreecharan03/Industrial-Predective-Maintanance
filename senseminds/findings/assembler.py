"""Deterministic Findings assembler (ADR-013).

A pure function: read validated engine results (Threshold, Health, Reliability),
apply deterministic interpretation rules, emit immutable `DERIVED` Findings. No
persistence, no orchestration, no side effects, no rule/ML/LLM logic. Given the
same inputs it always returns findings with the same ids (idempotent).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.engines.health.models import HealthResult
from senseminds.engines.reliability.models import ReliabilityResult
from senseminds.engines.threshold.models import ThresholdResult, ThresholdState
from senseminds.findings.enums import (
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
)
from senseminds.findings.identity import finding_id, identity_key
from senseminds.findings.models import Finding, ObservedWindow

ASSEMBLER_NAME = "findings"
ASSEMBLER_VERSION = "0.1.0"

# Deterministic interpretation thresholds (documented, not tuned to a target).
_MISSPECIFIED_PCT_OUTSIDE = 50.0
_DRIFT = 1.0
_FLATLINE_PCT = 5.0
_FLATLINE_WARN_PCT = 25.0
_UNTRUSTWORTHY_SCORE = 80.0

_UNKNOWN_CONF = Confidence(value=0.5, rationale="source confidence unavailable")


class FindingsError(RuntimeError):
    """Inputs to the assembler are inconsistent (e.g. different units/data)."""


@dataclass(frozen=True)
class _Ctx:
    equipment_key: str
    input_hash: str
    observed_window: ObservedWindow
    provenance: Provenance
    subsystem_of: Mapping[str, str]
    previous_by_identity: Mapping[str, Finding]


@dataclass(frozen=True)
class _Draft:
    finding_type: FindingType
    category: FindingCategory
    scope: FindingScope
    target_key: str
    severity: Severity
    summary: str
    detail: str
    confidence: Confidence
    evidence: tuple[Evidence, ...]
    source_engine: str


class FindingsAssembler:
    """Turn deterministic engine results into standardized DERIVED findings."""

    def assemble(
        self,
        *,
        threshold: ThresholdResult,
        reliability: ReliabilityResult,
        health: HealthResult,
        observed_window: ObservedWindow,
        subsystem_of: Mapping[str, str] | None = None,
        previous: tuple[Finding, ...] = (),
    ) -> tuple[Finding, ...]:
        units = {threshold.unit, reliability.unit, health.unit}
        if len(units) != 1:
            raise FindingsError(f"results span multiple units: {sorted(units)}")
        input_hashes = {
            threshold.provenance.input_hash,
            reliability.provenance.input_hash,
            health.provenance.input_hash,
        }
        if len(input_hashes) != 1:
            raise FindingsError("results were computed from different input data")

        unit = threshold.unit
        ctx = _Ctx(
            equipment_key=unit,
            input_hash=next(iter(input_hashes)),
            observed_window=observed_window,
            provenance=Provenance(
                engine=ASSEMBLER_NAME,
                engine_version=ASSEMBLER_VERSION,
                source_unit=unit,
                input_hash=next(iter(input_hashes)),
                produced_at=datetime.now(tz=UTC),
            ),
            subsystem_of=subsystem_of or {},
            previous_by_identity={f.identity_key: f for f in previous},
        )

        drafts: list[_Draft] = []
        drafts.extend(_threshold_drafts(threshold))
        drafts.extend(_reliability_drafts(reliability))
        drafts.extend(_health_drafts(health, unit))

        findings = [self._build(d, ctx) for d in drafts]
        findings.sort(
            key=lambda f: (f.category.value, f.scope.value, f.target_key, f.finding_type.value)
        )
        return tuple(findings)

    def _build(self, d: _Draft, ctx: _Ctx) -> Finding:
        idk = identity_key(ctx.equipment_key, d.finding_type, d.scope, d.target_key)
        fid = finding_id(idk, ctx.input_hash)
        prev = ctx.previous_by_identity.get(idk)
        supersedes = prev.finding_id if prev is not None and prev.finding_id != fid else None
        subsystem_key = (
            d.target_key
            if d.scope is FindingScope.SUBSYSTEM
            else ctx.subsystem_of.get(d.target_key)
            if d.scope is FindingScope.SENSOR
            else None
        )
        return Finding(
            finding_id=fid,
            identity_key=idk,
            finding_type=d.finding_type,
            category=d.category,
            scope=d.scope,
            origin=FindingOrigin.DERIVED,
            summary=d.summary,
            detail=d.detail,
            target_key=d.target_key,
            equipment_key=ctx.equipment_key,
            subsystem_key=subsystem_key,
            severity=d.severity,
            confidence=d.confidence,
            evidence=d.evidence,
            source_engine=d.source_engine,
            observed_window=ctx.observed_window,
            provenance=ctx.provenance,
            supersedes=supersedes,
        )


def _threshold_drafts(threshold: ThresholdResult) -> list[_Draft]:
    drafts: list[_Draft] = []
    for s in threshold.sensors:
        if s.history is not None and s.history.pct_outside >= _MISSPECIFIED_PCT_OUTSIDE:
            drafts.append(
                _Draft(
                    finding_type=FindingType.THRESHOLD_MISSPECIFIED,
                    category=FindingCategory.THRESHOLD,
                    scope=FindingScope.SENSOR,
                    target_key=s.sensor_key,
                    severity=Severity.WARNING,
                    summary=f"Operating threshold for {s.sensor_key} is inconsistent with history",
                    detail=s.evidence.historical_context or s.evidence.interpretation,
                    confidence=s.evidence.confidence,
                    evidence=(
                        Evidence(
                            artifact_id=threshold.artifact_id,
                            description=s.evidence.interpretation,
                            observed_value=s.history.pct_outside,
                        ),
                    ),
                    source_engine="threshold",
                )
            )
        if s.current_state in (ThresholdState.CRITICAL, ThresholdState.TRIP):
            drafts.append(
                _Draft(
                    finding_type=FindingType.THRESHOLD_CRITICAL,
                    category=FindingCategory.THRESHOLD,
                    scope=FindingScope.SENSOR,
                    target_key=s.sensor_key,
                    severity=Severity.CRITICAL,
                    summary=f"{s.sensor_key} reached a {s.current_state.value} threshold state",
                    detail=f"Latest reading {s.latest_value} breached a protection setpoint.",
                    confidence=s.evidence.confidence,
                    evidence=(
                        Evidence(
                            artifact_id=threshold.artifact_id,
                            description=f"current state {s.current_state.value}",
                            observed_value=s.latest_value,
                        ),
                    ),
                    source_engine="threshold",
                )
            )
    return drafts


def _reliability_drafts(reliability: ReliabilityResult) -> list[_Draft]:
    drafts: list[_Draft] = []
    for s in reliability.sensors:
        g = s.signals
        if g.drift is not None and g.drift > _DRIFT:
            drafts.append(
                _Draft(
                    finding_type=FindingType.RELIABILITY_DRIFT,
                    category=FindingCategory.RELIABILITY,
                    scope=FindingScope.SENSOR,
                    target_key=s.sensor_key,
                    severity=Severity.WARNING,
                    summary=f"{s.sensor_key} shows drift between first and second half of history",
                    detail=f"Drift {g.drift} (|2nd-half mean - 1st-half mean| / std).",
                    confidence=s.sensor_confidence,
                    evidence=(
                        Evidence(
                            artifact_id=reliability.artifact_id,
                            description="reliability drift signal",
                            observed_value=g.drift,
                        ),
                    ),
                    source_engine="reliability",
                )
            )
        if g.pct_in_flatline_runs >= _FLATLINE_PCT:
            drafts.append(
                _Draft(
                    finding_type=FindingType.RELIABILITY_FLATLINE,
                    category=FindingCategory.RELIABILITY,
                    scope=FindingScope.SENSOR,
                    target_key=s.sensor_key,
                    severity=(
                        Severity.WARNING
                        if g.pct_in_flatline_runs >= _FLATLINE_WARN_PCT
                        else Severity.INFO
                    ),
                    summary=f"{s.sensor_key} spends time flatlined (repeated identical readings)",
                    detail=f"{g.pct_in_flatline_runs}% of readings sit in runs of 5+ identical.",
                    confidence=s.sensor_confidence,
                    evidence=(
                        Evidence(
                            artifact_id=reliability.artifact_id,
                            description="flatline signal",
                            observed_value=g.pct_in_flatline_runs,
                        ),
                    ),
                    source_engine="reliability",
                )
            )
        if s.reliability_score < _UNTRUSTWORTHY_SCORE:
            drafts.append(
                _Draft(
                    finding_type=FindingType.SENSOR_UNTRUSTWORTHY,
                    category=FindingCategory.RELIABILITY,
                    scope=FindingScope.SENSOR,
                    target_key=s.sensor_key,
                    severity=Severity.WARNING,
                    summary=f"{s.sensor_key} reliability is low - treat its data with caution",
                    detail=f"Reliability score {s.reliability_score} (< {_UNTRUSTWORTHY_SCORE}).",
                    confidence=s.sensor_confidence,
                    evidence=(
                        Evidence(
                            artifact_id=reliability.artifact_id,
                            description="composite reliability score",
                            observed_value=s.reliability_score,
                        ),
                    ),
                    source_engine="reliability",
                )
            )
    return drafts


def _health_drafts(health: HealthResult, unit: str) -> list[_Draft]:
    drafts: list[_Draft] = []
    levels = [(FindingScope.EQUIPMENT, health.equipment)] + [
        (FindingScope.SUBSYSTEM, s) for s in health.subsystems
    ]
    for scope, hs in levels:
        if hs.severity is Severity.OK:
            continue
        drafts.append(
            _Draft(
                finding_type=FindingType.HEALTH_DEGRADED,
                category=FindingCategory.HEALTH,
                scope=scope,
                target_key=hs.target_key,
                severity=hs.severity,
                summary=f"{scope.value} '{hs.target_key}' health is reduced ({hs.score})",
                detail="; ".join(hs.contributing_factors) or "health below nominal",
                confidence=hs.confidence or _UNKNOWN_CONF,
                evidence=(
                    Evidence(
                        artifact_id=health.artifact_id,
                        description=f"{scope.value} health score",
                        observed_value=hs.score,
                    ),
                ),
                source_engine="health",
            )
        )
    return drafts
