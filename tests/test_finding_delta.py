"""Material-change policy (application/finding_delta.py) — pure, no DB.

Findings are append-only and finding_id derives from the input hash, so without a
materiality test every 30-second analysis re-records conditions that have not
changed. These tests pin down what counts as "changed".
"""

from __future__ import annotations

from datetime import UTC, datetime

from senseminds.application.finding_delta import is_material_change
from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
    ObservedWindow,
)

_T = datetime(2024, 1, 1, tzinfo=UTC)


def _f(*, summary="health is reduced (86.8)", severity=Severity.WARNING,
       value=86.8, confidence=0.9, fid="a") -> Finding:
    return Finding(
        finding_id=fid, identity_key="id-1", finding_type=FindingType.HEALTH_DEGRADED,
        category=FindingCategory.HEALTH, scope=FindingScope.EQUIPMENT,
        origin=FindingOrigin.DERIVED, summary=summary, detail="d",
        target_key="SC-126", equipment_key="SC-126", severity=severity,
        confidence=Confidence(value=confidence, rationale="r"),
        evidence=(Evidence(artifact_id="a1", description="score", observed_value=value),),
        source_engine="health", observed_window=ObservedWindow(start=_T, end=_T),
        provenance=Provenance(engine="health", engine_version="0.1.0",
                              source_unit="SC-126", input_hash=fid, produced_at=_T),
    )


def test_a_new_condition_is_always_recorded() -> None:
    assert is_material_change(None, _f()) is True


def test_identical_condition_is_not_recorded_again() -> None:
    assert is_material_change(_f(fid="a"), _f(fid="b")) is False  # new id, same truth


def test_noise_in_the_numbers_is_not_a_change() -> None:
    # the engines write the number into the prose; a 0.1 wobble is not news
    prev = _f(summary="health is reduced (86.8)", value=86.8)
    now = _f(summary="health is reduced (86.9)", value=86.9, fid="b")
    assert is_material_change(prev, now) is False


def test_a_real_move_in_the_value_is_recorded() -> None:
    prev = _f(summary="health is reduced (86.8)", value=86.8)
    now = _f(summary="health is reduced (52.1)", value=52.1, fid="b")
    assert is_material_change(prev, now) is True


def test_severity_change_is_always_recorded() -> None:
    assert is_material_change(_f(), _f(severity=Severity.CRITICAL, fid="b")) is True


def test_confidence_swing_is_recorded() -> None:
    assert is_material_change(_f(confidence=0.9), _f(confidence=0.5, fid="b")) is True
    assert is_material_change(_f(confidence=0.90), _f(confidence=0.92, fid="b")) is False


def test_different_wording_is_recorded() -> None:
    prev = _f(summary="health is reduced (86.8)")
    now = _f(summary="condenser fouling suspected (86.8)", fid="b")
    assert is_material_change(prev, now) is True
