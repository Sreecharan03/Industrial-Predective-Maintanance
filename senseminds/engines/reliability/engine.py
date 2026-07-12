"""Sensor Trust (Reliability) engine.

Completes the deterministic core (Phase-2 step11). Consumes `QualityResult`
(missing, fault-code) + `StatisticsResult` (std) + the series (flatline/noise/
drift/spike/oscillation), and produces a per-sensor trust verdict. The
`reliability_score` reproduces Phase-2 exactly (completeness + non-flatline +
no-fault-code); noise/drift/spike/oscillation are additional deterministic
trust signals that inform `sensor_confidence` but not the parity score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from senseminds.domain.value_objects import Confidence
from senseminds.engines.base import BaseEngine
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.quality.models import QualityResult
from senseminds.engines.reliability.models import (
    ReliabilityResult,
    ReliabilitySignals,
    SensorReliability,
)
from senseminds.engines.statistics.models import StatisticsResult
from senseminds.ingestion.models import IngestedSeries

# Phase-2 step11 score weights (do not change - parity).
_W_COMPLETENESS = 0.40
_W_FLATLINE = 0.35
_W_FAULT = 0.25

_SPIKE_STD_MULT = 5.0


def _flatline(series: pd.Series) -> tuple[int, float]:
    s = series.dropna().reset_index(drop=True)
    if len(s) < 2:
        return len(s), 0.0
    run_id = (s != s.shift()).cumsum()
    grp = s.groupby(run_id).transform("size")
    longest = int(grp.max())
    pct = round(100 * (grp[grp >= 5]).count() / len(s), 2)
    return longest, pct


def _noise(series: pd.Series, std: float | None) -> float | None:
    s = series.dropna()
    if len(s) < 3 or std is None or std < 1e-9:
        return None
    return round(s.diff().abs().mean() / std, 4)


def _drift(series: pd.Series, std: float | None) -> float | None:
    s = series.dropna().reset_index(drop=True)
    if len(s) < 10 or std is None or std < 1e-9:
        return None
    half = len(s) // 2
    return round(abs(s.iloc[half:].mean() - s.iloc[:half].mean()) / std, 4)


def _spikes(series: pd.Series, std: float | None) -> tuple[int, float]:
    s = series.dropna()
    if len(s) < 3 or std is None or std < 1e-9:
        return 0, 0.0
    count = int((s.diff().abs() > _SPIKE_STD_MULT * std).sum())
    return count, round(100 * count / len(s), 2)


def _oscillation(series: pd.Series, std: float | None) -> float | None:
    s = series.dropna()
    if len(s) < 3 or std is None or std < 1e-9:
        return None
    diffs = s.diff().dropna()
    signs = np.sign(diffs)
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0.0
    flips = int((signs.to_numpy()[1:] != signs.to_numpy()[:-1]).sum())
    return round(flips / (len(signs) - 1), 4)


def _score(missing_pct: float, flatline_pct: float, fault_pct: float) -> float:
    completeness = 1 - missing_pct / 100
    non_flatline = 1 - min(flatline_pct, 100) / 100
    no_fault = 1 - fault_pct / 100
    return round(
        100 * (_W_COMPLETENESS * completeness + _W_FLATLINE * non_flatline + _W_FAULT * no_fault),
        1,
    )


def _sensor_confidence(score: float, sig: ReliabilitySignals) -> Confidence:
    value = score / 100
    issues: list[str] = []
    if sig.drift is not None and sig.drift > 1.0:
        value *= 0.9
        issues.append(f"drift {sig.drift:.2f}")
    if sig.spike_pct > 1.0:
        value *= 0.9
        issues.append(f"{sig.spike_pct}% spikes")
    if sig.noise_level is not None and sig.noise_level > 1.0:
        value *= 0.9
        issues.append(f"noise {sig.noise_level}")
    if sig.oscillation_rate is not None and sig.oscillation_rate > 0.6:
        value *= 0.95
        issues.append("oscillatory")
    rationale = (
        f"reliability score {score}; "
        + ("extended concerns: " + "; ".join(issues) if issues else "no extra trust concerns")
    )
    return Confidence(value=max(0.0, min(1.0, round(value, 4))), rationale=rationale)


class ReliabilityEngine(BaseEngine):
    """Assess every sensor's trustworthiness for a unit."""

    name = "reliability"
    version = "0.1.0"

    def compute(
        self, series: IngestedSeries, quality: QualityResult, statistics: StatisticsResult
    ) -> ReliabilityResult:
        unit = series.manifest.unit
        if quality.unit != unit or statistics.unit != unit:
            raise EngineInputError(
                f"quality/statistics unit mismatch with series unit {unit!r}"
            )
        assessed = [
            self._assess(series.frame[key], key, quality, statistics)
            for key in series.manifest.sensor_keys
        ]
        assessed.sort(key=lambda s: s[0], reverse=True)  # score desc
        sensors = tuple(
            SensorReliability(
                sensor_key=key,
                rank=rank,
                reliability_score=score,
                sensor_confidence=_sensor_confidence(score, sig),
                signals=sig,
            )
            for rank, (score, sig, key) in enumerate(assessed, start=1)
        )
        self.log.info("reliability_assessed", extra={"unit": unit, "sensors": len(sensors)})
        return ReliabilityResult(
            artifact_id=f"{unit}__reliability",
            provenance=self.provenance_from_frame(unit, series.frame),
            unit=unit,
            sensors=sensors,
        )

    @staticmethod
    def _assess(
        column: pd.Series, key: str, quality: QualityResult, statistics: StatisticsResult
    ) -> tuple[float, ReliabilitySignals, str]:
        sq = quality.sensor(key)
        st = statistics.sensor(key)
        missing_pct = sq.missing_pct if sq else 0.0
        n_valid = sq.n_valid if sq else 0
        std = st.std if st else None

        longest, flat_pct = _flatline(column)
        fault_count = sq.fault_code_count if sq else 0
        fault_pct = round(100 * fault_count / n_valid, 2) if n_valid else 0.0
        spike_count, spike_pct = _spikes(column, std)

        signals = ReliabilitySignals(
            missing_pct=missing_pct,
            completeness_pct=round(100 - missing_pct, 2),
            longest_flatline_run=longest,
            pct_in_flatline_runs=flat_pct,
            fault_code_value=sq.fault_code_value if sq else None,
            fault_code_count=fault_count,
            fault_code_pct=fault_pct,
            noise_level=_noise(column, std),
            drift=_drift(column, std),
            spike_count=spike_count,
            spike_pct=spike_pct,
            oscillation_rate=_oscillation(column, std),
        )
        score = _score(missing_pct, flat_pct, fault_pct)
        return score, signals, key
