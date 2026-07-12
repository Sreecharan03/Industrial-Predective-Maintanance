"""ReadingValidation (ADR-019 R3) - pure, no DB required."""

from __future__ import annotations

from datetime import UTC, datetime

from senseminds.ingestion import QualityFlag, Reading, ReadingValidation

_T = datetime(2024, 1, 1, tzinfo=UTC)


def _r(**kw) -> Reading:
    base = {"unit": "SC-126", "sensor_key": "oil_pressure", "time": _T, "value": 1.0}
    base.update(kw)
    return Reading(**base)


def test_accepts_finite_reading() -> None:
    out = ReadingValidation("SC-126").validate([_r(value=208.77)])
    assert not out.rejected
    assert out.accepted[0].value == 208.77
    assert out.accepted[0].quality == QualityFlag.OK


def test_nan_becomes_missing_not_rejected() -> None:
    out = ReadingValidation("SC-126").validate([_r(value=float("nan"))])
    assert not out.rejected  # a logged-but-absent measurement is data, not garbage
    assert out.accepted[0].value is None
    assert out.accepted[0].quality == QualityFlag.MISSING


def test_rejects_infinite_value() -> None:
    out = ReadingValidation("SC-126").validate([_r(value=float("inf"))])
    assert not out.accepted
    assert "non-finite" in out.rejected[0].reason


def test_rejects_unit_mismatch() -> None:
    out = ReadingValidation("SC-126").validate([_r(unit="SC-114")])
    assert not out.accepted
    assert "unit mismatch" in out.rejected[0].reason


def test_rejects_missing_timestamp_and_key() -> None:
    out = ReadingValidation("SC-126").validate([_r(time=None), _r(sensor_key="")])
    assert len(out.rejected) == 2
    assert not out.accepted


def test_rejects_in_batch_duplicate() -> None:
    out = ReadingValidation("SC-126").validate([_r(value=1.0), _r(value=2.0)])
    assert len(out.accepted) == 1  # first wins
    assert len(out.rejected) == 1
    assert "duplicate" in out.rejected[0].reason
