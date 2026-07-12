"""Reading model + validation stage (ADR-019 D2, R3).

A `Reading` is one measurement (or its documented absence) for one sensor at one
instant - the atomic unit persisted to `sensor_history`. `ReadingValidation` is a
**pure** stage that runs before any sink: only validated readings reach the DB.

Design decision (parity-critical): a *missing measurement* (NaN/None value at a
real, logged timestamp) is **not** an invalid reading - it is a legitimate
observation of absence, persisted as a NULL value with `quality=MISSING`. This
preserves the exact observation grid, which downstream statistics / reliability
/ data-quality depend on for byte-identical results. Only *structurally* bad
readings (missing key/time, wrong unit, duplicate, non-finite ±inf) are rejected.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import IntEnum


class QualityFlag(IntEnum):
    """Reading quality. Extends as real quality signals are introduced."""

    OK = 0
    MISSING = 1  # timestamp logged, measurement absent (stored as NULL value)


@dataclass(frozen=True)
class Reading:
    """One sensor measurement (or documented absence) at one instant."""

    unit: str
    sensor_key: str
    time: datetime
    value: float | None
    quality: int = QualityFlag.OK
    source: str = "csv_bootstrap"


@dataclass(frozen=True)
class RejectedReading:
    """A reading dropped before persistence, with the reason (for observability)."""

    reading: Reading
    reason: str


@dataclass(frozen=True)
class ReadingValidationResult:
    """Accepted (persistable) readings + rejections."""

    accepted: list[Reading]
    rejected: list[RejectedReading]


def _is_missing_value(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


class ReadingValidation:
    """Validate readings for one target unit before they reach a sink.

    Checks per reading: missing fields (unit/sensor_key/time), unit consistency,
    obviously-invalid values (±inf), and in-batch duplicate `(unit, sensor_key,
    time)`. NaN/None values are accepted as `MISSING` (see module docstring).
    """

    def __init__(self, unit: str) -> None:
        self._unit = unit

    def validate(self, readings: Iterable[Reading]) -> ReadingValidationResult:
        accepted: list[Reading] = []
        rejected: list[RejectedReading] = []
        seen: set[tuple[str, str, datetime]] = set()
        for r in readings:
            reason = self._reject_reason(r, seen)
            if reason is not None:
                rejected.append(RejectedReading(r, reason))
                continue
            seen.add((r.unit, r.sensor_key, r.time))
            if _is_missing_value(r.value):
                accepted.append(replace(r, value=None, quality=QualityFlag.MISSING))
            else:
                accepted.append(r)
        return ReadingValidationResult(accepted, rejected)

    def _reject_reason(
        self, r: Reading, seen: set[tuple[str, str, datetime]]
    ) -> str | None:
        if not r.unit:
            return "missing unit"
        if not r.sensor_key:
            return "missing sensor_key"
        if r.time is None:
            return "missing timestamp"
        if r.unit != self._unit:
            return f"unit mismatch (reading {r.unit!r} != target {self._unit!r})"
        if isinstance(r.value, float) and math.isinf(r.value):
            return "non-finite value (inf)"
        if (r.unit, r.sensor_key, r.time) in seen:
            return "duplicate (unit, sensor_key, time)"
        return None
