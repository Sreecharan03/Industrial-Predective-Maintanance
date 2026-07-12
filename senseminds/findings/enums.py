"""Findings taxonomy enumerations (ADR-013 §3).

Three orthogonal classification axes (category / scope / origin) plus the
enumerable `FindingType` - the stable machine-readable key everything switches
on. New capabilities add types/origins without reshaping the taxonomy.
"""

from __future__ import annotations

from enum import StrEnum


class FindingCategory(StrEnum):
    """What the finding is about."""

    THRESHOLD = "threshold"
    RELIABILITY = "reliability"
    HEALTH = "health"
    RUNTIME = "runtime"
    ENVELOPE = "envelope"
    DATA_QUALITY = "data_quality"
    DIAGNOSTIC = "diagnostic"  # rule-derived equipment diagnosis
    VALIDATION = "validation"  # rule-derived platform-consistency finding (ADR-015 R3)
    ANOMALY = "anomaly"  # pattern-learning (future)


class FindingScope(StrEnum):
    """What level of the asset hierarchy the finding applies to."""

    SENSOR = "sensor"
    SUBSYSTEM = "subsystem"
    EQUIPMENT = "equipment"
    PLANT = "plant"


class FindingOrigin(StrEnum):
    """How the finding was produced (and thus how to treat it, e.g. for ML)."""

    DERIVED = "derived"  # deterministic from one engine verdict
    DIAGNOSED = "diagnosed"  # rule engine, multi-signal (future)
    LEARNED = "learned"  # pattern learning (future)


class FindingType(StrEnum):
    """The specific, enumerable kind of finding (the switch key)."""

    THRESHOLD_MISSPECIFIED = "threshold_misspecified"
    THRESHOLD_CRITICAL = "threshold_critical"
    HEALTH_DEGRADED = "health_degraded"
    RELIABILITY_DRIFT = "reliability_drift"
    RELIABILITY_FLATLINE = "reliability_flatline"
    SENSOR_UNTRUSTWORTHY = "sensor_untrustworthy"
    # --- rule-derived (DIAGNOSED) ---
    THRESHOLD_CONFIG_REVIEW_RECOMMENDED = "threshold_config_review_recommended"
    CONDENSER_FOULING_SUSPECTED = "condenser_fouling_suspected"
    # --- rule-derived (VALIDATION) ---
    CRITICAL_ON_UNTRUSTWORTHY_SENSOR = "critical_on_untrustworthy_sensor"
    # --- learned (LEARNED, Phase B) - hypotheses, never facts ---
    NOVELTY_ELEVATED = "novelty_elevated"
    OPERATING_REGIME_DISCOVERED = "operating_regime_discovered"
    FORECAST_THRESHOLD_APPROACH = "forecast_threshold_approach"
