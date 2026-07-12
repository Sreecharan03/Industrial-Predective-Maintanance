"""Validation: the Findings assembler must produce the known SC-126 engineering
verdicts from the real data (deterministic, explainable).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from senseminds.application import DeterministicPipeline
from senseminds.engines.health import HealthEngine
from senseminds.findings import FindingsAssembler, FindingScope, FindingType, ObservedWindow
from senseminds.ingestion import ProcessedCsvSource

_PROCESSED = Path(__file__).resolve().parents[2] / "Datasets" / "processed"

pytestmark = pytest.mark.skipif(
    not (_PROCESSED / "SC-126.csv").exists(), reason="Phase-1/2 data not available"
)


@pytest.fixture(scope="module")
def findings():  # noqa: ANN201
    ctx = DeterministicPipeline().run(ProcessedCsvSource(_PROCESSED).load("SC-126"))
    health = HealthEngine().compute(ctx)
    window = ObservedWindow(start=ctx.series.manifest.start, end=ctx.series.manifest.end)
    subsystem_of = {k: sub.key for sub in ctx.series.asset.subsystems for k in sub.sensor_keys}
    return FindingsAssembler().assemble(
        threshold=ctx.threshold,
        reliability=ctx.reliability,
        health=health,
        observed_window=window,
        subsystem_of=subsystem_of,
    )


def _has(findings, ftype, target) -> bool:  # noqa: ANN001
    return any(f.finding_type is ftype and f.target_key == target for f in findings)


def test_discharge_pressure_threshold_misspecified(findings) -> None:  # noqa: ANN001
    # 94.87% of readings outside 235-247; typical operation sits below -> mis-spec.
    assert _has(findings, FindingType.THRESHOLD_MISSPECIFIED, "discharge_pressure")
    assert _has(findings, FindingType.THRESHOLD_MISSPECIFIED, "oil_pressure")  # 52.65% outside
    assert _has(findings, FindingType.THRESHOLD_MISSPECIFIED, "loading_percentage")  # 61.02%


def test_condenser_drift_findings(findings) -> None:  # noqa: ANN001
    # Condenser temps drift ~1.05 over the year (seasonal / cooling-water).
    assert _has(findings, FindingType.RELIABILITY_DRIFT, "condenser_entering_temp")
    assert _has(findings, FindingType.RELIABILITY_DRIFT, "condenser_leaving_temp")


def test_loading_flatline_finding(findings) -> None:  # noqa: ANN001
    # Baseload machine pinned at 100% -> 9.76% flatlined.
    assert _has(findings, FindingType.RELIABILITY_FLATLINE, "loading_percentage")


def test_healthy_unit_has_no_critical_or_health_degraded(findings) -> None:  # noqa: ANN001
    # SC-126 real data is healthy: no trips, no equipment health-degraded finding.
    assert not any(f.finding_type is FindingType.THRESHOLD_CRITICAL for f in findings)
    assert not any(
        f.finding_type is FindingType.HEALTH_DEGRADED and f.scope is FindingScope.EQUIPMENT
        for f in findings
    )


def test_every_finding_has_evidence_and_provenance(findings) -> None:  # noqa: ANN001
    for f in findings:
        assert len(f.evidence) >= 1
        assert f.provenance.engine == "findings"
        assert f.origin.value == "derived"
