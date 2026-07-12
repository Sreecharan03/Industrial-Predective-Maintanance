"""Health engine - behaviour and contract tests (no Phase-2 parity: new capability)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from senseminds.application import DeterministicPipeline
from senseminds.domain.enums import Severity
from senseminds.engines.health import HealthEngine, HealthResult
from senseminds.ingestion import ProcessedCsvSource


def _context(tmp_path: Path, values: dict[str, list]):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    return DeterministicPipeline().run(series)


# ----------------------------- behaviour -----------------------------

def test_healthy_unit_scores_ok(tmp_path: Path) -> None:
    ctx = _context(
        tmp_path,
        {
            "Suction Pressure": list(20 + np.sin(np.linspace(0, 6 * np.pi, 200))),
            "Loading Percentage": [80.0] * 200,
        },
    )
    result = HealthEngine().compute(ctx)
    assert result.equipment.severity is Severity.OK
    assert result.equipment.score >= 80


def test_hierarchy_is_populated(tmp_path: Path) -> None:
    ctx = _context(tmp_path, {"Suction Pressure": [20.0] * 200, "Oil Pressure": [200.0] * 200})
    result = HealthEngine().compute(ctx)
    # equipment -> subsystems -> sensors all present
    assert result.equipment.scope == "equipment"
    assert {s.scope for s in result.subsystems} == {"subsystem"}
    assert result.sensor("suction_pressure") is not None
    assert result.subsystem("compression") is not None


def test_tripped_sensor_drives_critical(tmp_path: Path) -> None:
    # Discharge pressure latest reading above the trip setpoint (297).
    vals = [240.0] * 199 + [300.0]
    ctx = _context(tmp_path, {"Discharge Pressure": vals})
    result = HealthEngine().compute(ctx)
    sh = result.sensor("discharge_pressure")
    assert sh.severity is Severity.CRITICAL
    assert sh.score == 0.0
    # worst severity propagates up
    assert result.equipment.severity is Severity.CRITICAL


def test_health_carries_confidence_from_reliability(tmp_path: Path) -> None:
    ctx = _context(tmp_path, {"Suction Pressure": [20.0] * 200})
    sh = HealthEngine().compute(ctx).sensor("suction_pressure")
    assert sh.confidence is not None
    assert 0.0 <= sh.confidence.value <= 1.0
    assert sh.evidence  # traceable to reliability + threshold artifacts


def test_requires_reliability_and_threshold(tmp_path: Path) -> None:
    from senseminds.application import AnalysisContext, MissingDependencyError

    series = ProcessedCsvSource  # placeholder to build a bare context
    n = 50
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame(
        {"timestamp": [t.isoformat() for t in ts], "Suction Pressure": [20.0] * n}
    ).to_csv(tmp_path / "SC-126.csv", index=False)
    bare = AnalysisContext(unit="SC-126", series=series(tmp_path).load("SC-126"))
    with pytest.raises(MissingDependencyError, match="reliability"):
        HealthEngine().compute(bare)


# ----------------------------- contract -----------------------------

def test_result_is_immutable_and_serializable(tmp_path: Path) -> None:
    ctx = _context(tmp_path, {"Suction Pressure": [20.0] * 200})
    result = HealthEngine().compute(ctx)
    with pytest.raises(ValidationError):
        result.unit = "x"  # type: ignore[misc]
    restored = HealthResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert result.provenance.engine == "health"
