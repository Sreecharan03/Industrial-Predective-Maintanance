"""Sensor Trust (Reliability) engine result models.

Answers one question for every downstream consumer (Health, Rules, Pattern
Learning, LLM): *should I trust this sensor before using its data?* The
`reliability_score` is the Phase-2-compatible composite (completeness +
non-flatline + no-fault-code); the extended signals (noise, drift, spike,
oscillation) and the holistic `sensor_confidence` are the additional trust
assessment layered on top. Immutable.
"""

from __future__ import annotations

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.results import EngineResult
from senseminds.domain.value_objects import Confidence


class ReliabilitySignals(FrozenModel):
    """Every trust signal computed for one sensor."""

    missing_pct: float = Field(ge=0.0, le=100.0)
    completeness_pct: float = Field(ge=0.0, le=100.0)
    longest_flatline_run: int = Field(ge=0)
    pct_in_flatline_runs: float = Field(ge=0.0, le=100.0, description="% of readings in runs >= 5.")
    fault_code_value: float | None = None
    fault_code_count: int = Field(default=0, ge=0)
    fault_code_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    noise_level: float | None = Field(default=None, description="Mean |diff| / std; ~0 smooth.")
    drift: float | None = Field(default=None, description="|2nd-half mean - 1st-half mean| / std.")
    spike_count: int = Field(default=0, ge=0, description="Point jumps > 5*std.")
    spike_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    oscillation_rate: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Fraction of consecutive diffs that flip sign."
    )


class SensorReliability(FrozenModel):
    """The trust verdict for one sensor."""

    sensor_key: str
    rank: int = Field(ge=1, description="1 = most reliable within this unit.")
    reliability_score: float = Field(ge=0.0, le=100.0, description="Phase-2 composite score.")
    sensor_confidence: Confidence = Field(description="Holistic 'should I trust this sensor?'")
    signals: ReliabilitySignals


class ReliabilityResult(EngineResult):
    """Per-sensor trust verdicts for a unit, ranked most to least reliable."""

    unit: str
    sensors: tuple[SensorReliability, ...]

    def sensor(self, key: str) -> SensorReliability | None:
        return next((s for s in self.sensors if s.sensor_key == key), None)
