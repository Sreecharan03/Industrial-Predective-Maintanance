"""Threshold engine.

The single source of truth for threshold evaluation in SenseMinds. Consumes an
`IngestedSeries` (for breach counting) and an `OperatingEnvelopeResult` (for
the P5-P95 window used in engineering interpretation). Owns: lookup, breach
detection, current-state evaluation, protection-setpoint counting, historical
summary, and evidence generation. Computes NO statistics, envelopes, runtime,
or health. Operating-range breach counts reproduce Phase-1 exactly
(tests/test_parity_threshold.py).
"""

from __future__ import annotations

import pandas as pd

from senseminds.domain.enums import Severity, ThresholdStatus
from senseminds.domain.value_objects import Confidence
from senseminds.engines.base import BaseEngine
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.operating_envelope.models import EnvelopeBands, OperatingEnvelopeResult
from senseminds.engines.threshold.config import threshold_spec_for
from senseminds.engines.threshold.models import (
    ProtectionCount,
    SensorThresholdResult,
    ThresholdEvidence,
    ThresholdHistory,
    ThresholdResult,
    ThresholdSpec,
    ThresholdState,
)
from senseminds.ingestion.models import IngestedSeries


def _interpretation(pct_outside: float) -> str:
    """Engineering reading of a breach rate (mirrors Phase-1 threshold validation)."""
    if pct_outside >= 50:
        return (
            f"Most historical readings ({pct_outside}%) fall outside this threshold - it likely "
            "represents a protection/design setpoint or requires engineering review, not the "
            "observed operating band. Not evidence of a fault."
        )
    if pct_outside >= 20:
        return (
            f"A substantial minority ({pct_outside}%) fall outside - the threshold may need "
            "engineering review against current operating conditions."
        )
    if pct_outside >= 5:
        return (
            f"Modest excursions ({pct_outside}%), consistent with normal transients "
            "(startup/shutdown/load changes)."
        )
    return "Consistent with the observed historical operating range - the threshold appears valid."


def _historical_context(low: float | None, high: float | None, bands: EnvelopeBands | None) -> str:
    """Locate the threshold relative to historically typical operation (P25-P75).

    This is what separates an *engineering-limit violation* (readings genuinely
    abnormal vs. the observed norm) from *historically-typical behaviour* (the
    machine simply operates outside a threshold that does not describe its real
    operating band).
    """
    if bands is None or bands.typical_range.low is None or bands.typical_range.high is None:
        return "No operating-envelope context available for this sensor."
    tp25, tp75 = bands.typical_range.low, bands.typical_range.high
    typ = f"P25-P75 = {tp25:g}-{tp75:g}"
    if high is not None and tp25 > high:
        return (
            f"Historically typical operation ({typ}) sits ABOVE the threshold max ({high:g}): the "
            "machine normally runs beyond this limit, so it reads as a protection/design setpoint "
            "or a mis-set operating limit, not the operating band."
        )
    if low is not None and tp75 < low:
        return (
            f"Historically typical operation ({typ}) sits BELOW the threshold min ({low:g}): the "
            "machine rarely reaches this band, so the limit does not describe normal operation."
        )
    inside = (low is None or tp25 >= low) and (high is None or tp75 <= high)
    if inside:
        return (
            f"Historically typical operation ({typ}) sits INSIDE this threshold - the limit "
            "encloses normal operation, so breaches are genuine excursions from the observed norm."
        )
    return (
        f"Historically typical operation ({typ}) partially overlaps this threshold - some normal "
        "operation lies outside the limit; engineering review recommended."
    )


class ThresholdEngine(BaseEngine):
    """Evaluate every sensor of a unit against its thresholds."""

    name = "threshold"
    version = "0.1.0"

    def compute(
        self, series: IngestedSeries, envelope: OperatingEnvelopeResult
    ) -> ThresholdResult:
        unit = series.manifest.unit
        if envelope.unit != unit:
            raise EngineInputError(
                f"envelope unit {envelope.unit!r} does not match series unit {unit!r}"
            )
        n_rows = series.manifest.n_rows
        sensors = [
            self._evaluate_sensor(series, envelope, key, n_rows)
            for key in series.manifest.sensor_keys
        ]
        self.log.info("thresholds_evaluated", extra={"unit": unit, "sensors": len(sensors)})
        return ThresholdResult(
            artifact_id=f"{unit}__threshold",
            provenance=self.provenance_from_frame(unit, series.frame),
            unit=unit,
            sensors=tuple(sensors),
        )

    def _evaluate_sensor(
        self, series: IngestedSeries, envelope: OperatingEnvelopeResult, key: str, n_rows: int
    ) -> SensorThresholdResult:
        sensor = series.asset.sensor(key)
        if sensor is None:
            raise EngineInputError(f"sensor {key!r} not found in unit catalog")
        status, spec = threshold_spec_for(series.manifest.unit, sensor)

        if status is not ThresholdStatus.AVAILABLE or spec.operating is None:
            return self._unthresholded(key, status, spec)
        env_sensor = envelope.sensor(key)
        bands = env_sensor.bands if env_sensor is not None else None
        return self._thresholded(series.frame[key], key, spec, n_rows, bands)

    def _unthresholded(
        self, key: str, status: ThresholdStatus, spec: ThresholdSpec
    ) -> SensorThresholdResult:
        note = {
            ThresholdStatus.MISSING: "No threshold table supplied for this unit.",
            ThresholdStatus.REQUIRES_MANUAL_VALIDATION: (
                "Unit has a threshold table but it does not cover this sensor; "
                "manual validation required."
            ),
        }.get(status, "No threshold available.")
        return SensorThresholdResult(
            sensor_key=key,
            status=status,
            spec=spec,
            latest_value=None,
            current_state=ThresholdState.UNKNOWN,
            severity=Severity.INFO,
            active_violations=(),
            history=None,
            evidence=ThresholdEvidence(
                threshold_evaluated="none",
                observed_value=None,
                threshold_value="not supplied",
                interpretation=note,
                confidence=Confidence(value=0.0, rationale="No threshold to evaluate against."),
                assumptions=(),
                limitations=("No range-check performed; no threshold defined.",),
            ),
        )

    def _thresholded(
        self,
        column: pd.Series,
        key: str,
        spec: ThresholdSpec,
        n_rows: int,
        bands: EnvelopeBands | None,
    ) -> SensorThresholdResult:
        band = spec.operating
        low, high = band.low, band.high
        valid = column.dropna()
        n_valid = len(valid)

        outside_mask = pd.Series(False, index=valid.index)
        if low is not None:
            outside_mask |= valid < low
        if high is not None:
            outside_mask |= valid > high
        n_outside = int(outside_mask.sum())
        n_within = n_valid - n_outside
        pct_within = round(100 * n_within / n_valid, 2) if n_valid else 0.0
        pct_outside = round(100 * n_outside / n_valid, 2) if n_valid else 0.0

        protection_counts = self._protection_counts(valid, spec, n_valid)

        latest_value = float(valid.iloc[-1]) if n_valid else None
        state, severity, violations = self._current_state(latest_value, spec)

        history = ThresholdHistory(
            n_evaluated=n_valid,
            n_within_operating=n_within,
            n_outside_operating=n_outside,
            pct_within=pct_within,
            pct_outside=pct_outside,
            protection_counts=protection_counts,
        )
        coverage = round(100 * n_valid / n_rows, 2) if n_rows else 0.0
        limitations = ["Evaluated against the operating range; transient states not excluded."]
        if coverage < 90:
            limitations.append(f"Data coverage is {coverage}% - partial history.")
        evidence = ThresholdEvidence(
            threshold_evaluated=f"operating range [{low}, {high}]"
            + (f" + {len(spec.protection)} protection setpoint(s)" if spec.protection else ""),
            observed_value=latest_value,
            threshold_value=f"{low} to {high}",
            interpretation=_interpretation(pct_outside),
            historical_context=_historical_context(low, high, bands),
            confidence=Confidence(
                value=max(0.0, min(1.0, coverage / 100)),
                rationale=f"{coverage}% coverage ({n_valid} of {n_rows} readings evaluated).",
            ),
            assumptions=(
                "Threshold applies across the whole analysed window.",
                "A single equipment variant / setpoint revision over the window.",
            ),
            limitations=tuple(limitations),
        )
        return SensorThresholdResult(
            sensor_key=key,
            status=ThresholdStatus.AVAILABLE,
            spec=spec,
            latest_value=latest_value,
            current_state=state,
            severity=severity,
            active_violations=violations,
            history=history,
            evidence=evidence,
        )

    @staticmethod
    def _protection_counts(
        valid: pd.Series, spec: ThresholdSpec, n_valid: int
    ) -> tuple[ProtectionCount, ...]:
        counts: list[ProtectionCount] = []
        for sp in spec.protection:
            breached = valid >= sp.level if sp.direction == "high" else valid <= sp.level
            cnt = int(breached.sum())
            counts.append(
                ProtectionCount(
                    name=sp.name,
                    level=sp.level,
                    direction=sp.direction,
                    count=cnt,
                    pct_of_readings=round(100 * cnt / n_valid, 2) if n_valid else 0.0,
                )
            )
        return tuple(counts)

    @staticmethod
    def _current_state(
        value: float | None, spec: ThresholdSpec
    ) -> tuple[ThresholdState, Severity, tuple[str, ...]]:
        if value is None or spec.operating is None:
            return ThresholdState.UNKNOWN, Severity.INFO, ()
        band = spec.operating
        violations: list[str] = []
        # protection setpoints, most-severe first
        trip = next((s for s in spec.protection if s.name == "trip"), None)
        breached_high = [s for s in spec.protection if s.direction == "high" and value >= s.level]
        breached_low = [s for s in spec.protection if s.direction == "low" and value <= s.level]
        for s in (*breached_high, *breached_low):
            violations.append(s.name)

        if band.high is not None and value > band.high:
            violations.insert(0, "above operating max")
        if band.low is not None and value < band.low:
            violations.insert(0, "below operating min")

        if trip is not None and value >= trip.level:
            return ThresholdState.TRIP, Severity.CRITICAL, tuple(violations)
        if breached_high or breached_low:
            return ThresholdState.CRITICAL, Severity.CRITICAL, tuple(violations)
        if violations:
            return ThresholdState.OUTSIDE_OPERATING, Severity.WARNING, tuple(violations)
        return ThresholdState.WITHIN_RANGE, Severity.OK, ()
