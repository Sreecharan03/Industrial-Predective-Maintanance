"""Rule Engine - behaviour, contract, conflict, reasoning-chain, determinism."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from senseminds.application import DeterministicPipeline
from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.engines.health import HealthEngine
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingsAssembler,
    FindingScope,
    FindingType,
    ObservedWindow,
)
from senseminds.findings.identity import finding_id, identity_key
from senseminds.ingestion import ProcessedCsvSource
from senseminds.rules import DEFAULT_RULES, RuleContext, RuleEvaluator

_REFRIG = "refrigeration_screw_compressor"
_CAT = {
    FindingType.THRESHOLD_MISSPECIFIED: FindingCategory.THRESHOLD,
    FindingType.THRESHOLD_CRITICAL: FindingCategory.THRESHOLD,
    FindingType.HEALTH_DEGRADED: FindingCategory.HEALTH,
    FindingType.RELIABILITY_DRIFT: FindingCategory.RELIABILITY,
    FindingType.SENSOR_UNTRUSTWORTHY: FindingCategory.RELIABILITY,
}


def _derived(
    ftype: FindingType, target: str, *, scope: FindingScope = FindingScope.SENSOR,
    severity: Severity = Severity.WARNING, confidence: float = 0.9,
    equipment: str = "SC-126", input_hash: str = "h",
) -> Finding:
    idk = identity_key(equipment, ftype, scope, target)
    return Finding(
        finding_id=finding_id(idk, input_hash), identity_key=idk, finding_type=ftype,
        category=_CAT.get(ftype, FindingCategory.DATA_QUALITY), scope=scope,
        origin=FindingOrigin.DERIVED, summary=f"{ftype.value} on {target}", detail="",
        target_key=target, equipment_key=equipment, severity=severity,
        confidence=Confidence(value=confidence, rationale="test"),
        evidence=(Evidence(artifact_id="a1", description="x", observed_value=1.0),),
        source_engine="test", observed_window=ObservedWindow(),
        provenance=Provenance(engine="test", engine_version="0.1.0", source_unit=equipment,
                              input_hash=input_hash, produced_at=datetime(2026, 7, 10, tzinfo=UTC)),
    )


def _ctx(**kw) -> RuleContext:  # noqa: ANN003
    return RuleContext(
        unit=kw.get("unit", "SC-126"), equipment_class=kw.get("equipment_class", _REFRIG),
        input_hash=kw.get("input_hash", "h"),
        observed_window=ObservedWindow(), reliability=kw.get("reliability", {}),
        subsystem_of=kw.get("subsystem_of", {}),
    )


_EVAL = RuleEvaluator(DEFAULT_RULES)


# ----------------------------- behaviour -----------------------------

def test_config_rule_fires_on_misspecified_threshold() -> None:
    findings = [_derived(FindingType.THRESHOLD_MISSPECIFIED, "discharge_pressure")]
    out = _EVAL.evaluate(findings, _ctx())
    assert any(f.finding_type is FindingType.THRESHOLD_CONFIG_REVIEW_RECOMMENDED for f in out)
    diag = out[0]
    assert diag.origin is FindingOrigin.DIAGNOSED
    assert diag.category is FindingCategory.DIAGNOSTIC


def test_config_rule_blocked_by_critical() -> None:
    findings = [
        _derived(FindingType.THRESHOLD_MISSPECIFIED, "discharge_pressure"),
        _derived(FindingType.THRESHOLD_CRITICAL, "discharge_pressure", severity=Severity.CRITICAL),
    ]
    out = _EVAL.evaluate(findings, _ctx())
    # excluded finding present -> config rule must not fire
    assert not any(f.finding_type is FindingType.THRESHOLD_CONFIG_REVIEW_RECOMMENDED for f in out)


def test_diagnostic_rule_fires_on_synthetic() -> None:
    findings = [
        _derived(FindingType.THRESHOLD_CRITICAL, "discharge_pressure", severity=Severity.CRITICAL),
        _derived(FindingType.HEALTH_DEGRADED, "condenser", scope=FindingScope.SUBSYSTEM),
    ]
    out = _EVAL.evaluate(findings, _ctx())
    assert any(f.finding_type is FindingType.CONDENSER_FOULING_SUSPECTED for f in out)


def test_validation_rule_fires_on_critical_untrustworthy() -> None:
    findings = [
        _derived(FindingType.THRESHOLD_CRITICAL, "oil_pressure", severity=Severity.CRITICAL),
        _derived(FindingType.SENSOR_UNTRUSTWORTHY, "oil_pressure"),
    ]
    out = _EVAL.evaluate(findings, _ctx())
    val = [f for f in out if f.finding_type is FindingType.CRITICAL_ON_UNTRUSTWORTHY_SENSOR]
    assert val and val[0].category is FindingCategory.VALIDATION


# ----------------------------- confidence / reliability ---------------

def test_reliability_discounts_confidence() -> None:
    findings = [
        _derived(FindingType.THRESHOLD_CRITICAL, "discharge_pressure", severity=Severity.CRITICAL),
        _derived(FindingType.HEALTH_DEGRADED, "condenser", scope=FindingScope.SUBSYSTEM),
    ]
    trusted = _EVAL.evaluate(findings, _ctx(reliability={"discharge_pressure": 1.0}))
    drifting = _EVAL.evaluate(findings, _ctx(reliability={"discharge_pressure": 0.5}))
    ct = next(f for f in trusted if f.finding_type is FindingType.CONDENSER_FOULING_SUSPECTED)
    cd = next(f for f in drifting if f.finding_type is FindingType.CONDENSER_FOULING_SUSPECTED)
    assert cd.confidence.value < ct.confidence.value


# ----------------------------- reasoning chain ------------------------

def test_reasoning_chain_persisted() -> None:
    trigger = _derived(FindingType.THRESHOLD_MISSPECIFIED, "discharge_pressure")
    out = _EVAL.evaluate([trigger], _ctx())
    diag = next(f for f in out if f.finding_type is FindingType.THRESHOLD_CONFIG_REVIEW_RECOMMENDED)
    assert trigger.identity_key in diag.triggered_by
    assert diag.evidence and "triggered by" in diag.evidence[0].description


# ----------------------------- conflict resolution --------------------

def test_conflict_resolution_ranks_by_priority() -> None:
    # untrustworthy critical sensor (validation, prio 90) + degraded health
    # (condenser diagnostic, prio 60) both fire -> validation ranks first.
    findings = [
        _derived(FindingType.THRESHOLD_CRITICAL, "discharge_pressure", severity=Severity.CRITICAL),
        _derived(FindingType.SENSOR_UNTRUSTWORTHY, "discharge_pressure"),
        _derived(FindingType.HEALTH_DEGRADED, "condenser", scope=FindingScope.SUBSYSTEM),
    ]
    out = _EVAL.evaluate(findings, _ctx())
    assert out[0].finding_type is FindingType.CRITICAL_ON_UNTRUSTWORTHY_SENSOR


# ----------------------------- determinism ----------------------------

def test_determinism() -> None:
    findings = [_derived(FindingType.THRESHOLD_MISSPECIFIED, "discharge_pressure")]
    a = _EVAL.evaluate(findings, _ctx())
    b = _EVAL.evaluate(findings, _ctx())
    assert [f.finding_id for f in a] == [f.finding_id for f in b]


def test_no_diagnoses_when_no_pattern() -> None:
    findings = [
        _derived(FindingType.RELIABILITY_FLATLINE, "loading_percentage", severity=Severity.INFO)
    ]
    assert _EVAL.evaluate(findings, _ctx()) == ()


# ----------------------------- contract -------------------------------

def test_diagnosed_finding_is_immutable_and_serializable() -> None:
    out = _EVAL.evaluate([_derived(FindingType.THRESHOLD_MISSPECIFIED, "x")], _ctx())
    f = out[0]
    with pytest.raises(ValidationError):
        f.severity = Severity.CRITICAL  # type: ignore[misc]
    assert Finding.model_validate_json(f.model_dump_json()) == f
    assert f.provenance.engine == "rule_engine"


# ----------------------------- SC-126 real ----------------------------

@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "Datasets" / "processed" / "SC-126.csv").exists(),
    reason="Phase-1/2 data not available",
)
def test_sc126_produces_threshold_config_review() -> None:
    processed = Path(__file__).resolve().parents[2] / "Datasets" / "processed"
    ctx = DeterministicPipeline().run(ProcessedCsvSource(processed).load("SC-126"))
    health = HealthEngine().compute(ctx)
    window = ObservedWindow(start=ctx.series.manifest.start, end=ctx.series.manifest.end)
    subsystem_of = {k: sub.key for sub in ctx.series.asset.subsystems for k in sub.sensor_keys}
    findings = FindingsAssembler().assemble(
        threshold=ctx.threshold, reliability=ctx.reliability, health=health,
        observed_window=window, subsystem_of=subsystem_of,
    )
    reliability = {s.sensor_key: s.sensor_confidence.value for s in ctx.reliability.sensors}
    rctx = RuleContext(
        unit="SC-126", equipment_class=ctx.series.asset.equipment_class.value,
        input_hash=ctx.threshold.provenance.input_hash, observed_window=window,
        reliability=reliability, subsystem_of=subsystem_of,
    )
    diagnoses = RuleEvaluator(DEFAULT_RULES).evaluate(findings, rctx)
    targets = {
        f.target_key for f in diagnoses
        if f.finding_type is FindingType.THRESHOLD_CONFIG_REVIEW_RECOMMENDED
    }
    assert {"discharge_pressure", "oil_pressure", "loading_percentage"} <= targets
    # SC-126 is healthy: no equipment fault diagnosis
    assert not any(f.finding_type is FindingType.CONDENSER_FOULING_SUSPECTED for f in diagnoses)
