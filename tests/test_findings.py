"""Engineering Findings layer - behaviour and contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
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
    finding_id,
    identity_key,
)
from senseminds.ingestion import ProcessedCsvSource

_ASSEMBLER = FindingsAssembler()


def _assemble(tmp_path: Path, values: dict[str, list], previous: tuple = ()) -> tuple[Finding, ...]:
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    ctx = DeterministicPipeline().run(ProcessedCsvSource(tmp_path).load("SC-126"))
    health = HealthEngine().compute(ctx)
    window = ObservedWindow(start=ctx.series.manifest.start, end=ctx.series.manifest.end)
    subsystem_of = {
        k: sub.key for sub in ctx.series.asset.subsystems for k in sub.sensor_keys
    }
    return _ASSEMBLER.assemble(
        threshold=ctx.threshold,
        reliability=ctx.reliability,
        health=health,
        observed_window=window,
        subsystem_of=subsystem_of,
        previous=previous,
    )


def _types(findings: tuple[Finding, ...], target: str) -> set[FindingType]:
    return {f.finding_type for f in findings if f.target_key == target}


# ----------------------------- behaviour -----------------------------

def test_threshold_misspecified(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Discharge Pressure": [200.0] * 200})  # below 235-247
    assert FindingType.THRESHOLD_MISSPECIFIED in _types(findings, "discharge_pressure")


def test_threshold_critical(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Discharge Pressure": [240.0] * 199 + [300.0]})  # >trip 297
    crit = [f for f in findings if f.finding_type is FindingType.THRESHOLD_CRITICAL]
    assert crit and crit[0].severity is Severity.CRITICAL


def test_degraded_health(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Discharge Pressure": [240.0] * 199 + [300.0]})
    degraded = [f for f in findings if f.finding_type is FindingType.HEALTH_DEGRADED]
    assert any(f.scope is FindingScope.EQUIPMENT for f in degraded)


def test_sensor_drift(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Suction Pressure": list(np.linspace(10, 30, 200))})
    assert FindingType.RELIABILITY_DRIFT in _types(findings, "suction_pressure")


def test_flatline_sensor(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Suction Pressure": [17.0] * 200})
    assert FindingType.RELIABILITY_FLATLINE in _types(findings, "suction_pressure")


def test_duplicate_findings_are_deduplicated(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Discharge Pressure": [200.0] * 200})
    ids = [f.finding_id for f in findings]
    assert len(ids) == len(set(ids))  # no duplicate finding_ids in one run


def test_idempotent_reruns(tmp_path: Path) -> None:
    a = _assemble(tmp_path, {"Discharge Pressure": [200.0] * 200})
    b = _assemble(tmp_path, {"Discharge Pressure": [200.0] * 200})
    assert {f.finding_id for f in a} == {f.finding_id for f in b}
    assert all(f.supersedes is None for f in b)  # identical data -> no supersession


def test_supersession(tmp_path: Path) -> None:
    a = _assemble(tmp_path, {"Discharge Pressure": [200.0] * 200})
    b = _assemble(tmp_path, {"Discharge Pressure": [210.0] * 200}, previous=a)  # still misspecified
    prev = {f.identity_key: f.finding_id for f in a}
    superseders = [f for f in b if f.identity_key in prev and f.finding_id != prev[f.identity_key]]
    assert superseders
    assert all(f.supersedes == prev[f.identity_key] for f in superseders)


def test_confidence_propagation(tmp_path: Path) -> None:
    findings = _assemble(tmp_path, {"Suction Pressure": list(np.linspace(10, 30, 200))})
    drift = next(f for f in findings if f.finding_type is FindingType.RELIABILITY_DRIFT)
    # confidence carries the source (reliability) confidence, not a fresh value
    assert 0.0 <= drift.confidence.value <= 1.0
    assert "reliability" in drift.confidence.rationale.lower()


# ----------------------------- contract -----------------------------

def _valid_kwargs() -> dict:
    return {
        "finding_id": "fid123",
        "identity_key": "idk123",
        "finding_type": FindingType.THRESHOLD_MISSPECIFIED,
        "category": FindingCategory.THRESHOLD,
        "scope": FindingScope.SENSOR,
        "origin": FindingOrigin.DERIVED,
        "summary": "threshold inconsistent with history",
        "detail": "typical operation sits below the threshold",
        "target_key": "discharge_pressure",
        "equipment_key": "SC-126",
        "severity": Severity.WARNING,
        "confidence": Confidence(value=0.9, rationale="coverage 99%"),
        "evidence": (Evidence(artifact_id="a1", description="pct outside", observed_value=94.87),),
        "source_engine": "threshold",
        "observed_window": ObservedWindow(),
        "provenance": Provenance(
            engine="findings",
            engine_version="0.1.0",
            source_unit="SC-126",
            input_hash="h",
            produced_at=datetime(2026, 7, 10, tzinfo=UTC),
        ),
    }


def test_finding_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Finding(**{**_valid_kwargs(), "evidence": ()})


def test_finding_requires_provenance() -> None:
    kwargs = _valid_kwargs()
    del kwargs["provenance"]
    with pytest.raises(ValidationError):
        Finding(**kwargs)


def test_finding_is_immutable() -> None:
    f = Finding(**_valid_kwargs())
    with pytest.raises(ValidationError):
        f.severity = Severity.CRITICAL  # type: ignore[misc]


def test_finding_serialization_round_trip() -> None:
    f = Finding(**_valid_kwargs())
    assert Finding.model_validate_json(f.model_dump_json()) == f


def test_finding_schema_is_stable() -> None:
    assert set(Finding.model_fields) == {
        "finding_id", "identity_key", "finding_type", "category", "scope", "origin",
        "summary", "detail", "target_key", "equipment_key", "subsystem_key",
        "severity", "confidence", "evidence", "source_engine", "observed_window",
        "provenance", "supersedes", "triggered_by",
    }


def test_deterministic_identity() -> None:
    drift, sensor = FindingType.RELIABILITY_DRIFT, FindingScope.SENSOR
    a = identity_key("SC-126", drift, sensor, "oil_temp")
    assert a == identity_key("SC-126", drift, sensor, "oil_temp")  # stable across calls
    assert identity_key("SC-126", drift, sensor, "oil_pressure") != a  # different target
    # asset is part of identity: same condition on different equipment is distinct
    assert identity_key("COM-110", drift, sensor, "oil_pressure") != identity_key(
        "COM-102", drift, sensor, "oil_pressure"
    )
    assert finding_id(a, "hash1") != finding_id(a, "hash2")  # different data -> new id
    assert finding_id(a, "hash1") == finding_id(a, "hash1")  # same data -> same id
