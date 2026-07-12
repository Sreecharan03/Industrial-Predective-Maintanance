"""Operating-envelope result models.

Public contract for the Operating Envelope engine. Immutable (frozen) and
composed of three separable concerns so downstream consumers see clean domain
concepts and never engine internals:

  EnvelopeBands    - the domain output (where the machine normally operates)
  EnvelopeEvidence - why the envelope is trustworthy (coverage, confidence)
  Provenance       - which engine/version/input produced it (on EngineResult)

No field names reference the algorithm (histogram/KDE) - consumers depend on
"normal operating window" / "most-frequent band", not on how they were found.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.results import EngineResult
from senseminds.domain.value_objects import Confidence


class Band(FrozenModel):
    """A closed operating band [low, high]; either bound may be unknown."""

    low: float | None = None
    high: float | None = None


class ModeBand(FrozenModel):
    """The most frequently observed operating band and its share of readings."""

    low: float
    high: float
    share_pct: float = Field(ge=0.0, le=100.0, description="% of readings in this band.")


class RareRegion(FrozenModel):
    """The seldom-visited edges of operation (low tail / high tail)."""

    low_end: float | None = Field(default=None, description="Upper bound of the rare low tail.")
    high_start: float | None = Field(default=None, description="Lower bound of the rare high tail.")
    pct_of_readings: float = Field(ge=0.0, le=100.0, description="% of readings that are rare.")


class EnvelopeBands(FrozenModel):
    """Domain output: where a sensor normally operates (all from history)."""

    normal_window: Band = Field(description="P5-P95: the normal operating window.")
    typical_range: Band = Field(description="P25-P75: the typical (interquartile) range.")
    median: float | None = None
    iqr: float | None = None
    cv_pct: float | None = None
    mode_band: ModeBand | None = Field(
        default=None, description="Most-frequent operating band; None if too sparse/flat."
    )
    rare_region: RareRegion | None = Field(
        default=None, description="Seldom-visited operating edges; None if none stand out."
    )


class EnvelopeEvidence(FrozenModel):
    """Why this envelope can (or cannot) be trusted - for the LLM to cite.

    All values are sourced from the consumed StatisticsResult / manifest, not
    recomputed here.
    """

    sample_count: int = Field(ge=0, description="Valid readings the envelope is based on.")
    coverage_pct: float = Field(ge=0.0, le=100.0, description="Valid readings / total rows.")
    missing_pct: float = Field(ge=0.0, le=100.0)
    confidence: Confidence
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)


class SensorEnvelope(FrozenModel):
    """One sensor's operating envelope: domain bands + trust evidence."""

    sensor_key: str
    bands: EnvelopeBands
    evidence: EnvelopeEvidence


class OperatingEnvelopeResult(EngineResult):
    """Operating envelopes for every sensor of a unit (immutable)."""

    unit: str
    window_start: datetime | None = Field(default=None, description="Start of analysed history.")
    window_end: datetime | None = Field(default=None, description="End of analysed history.")
    sensors: tuple[SensorEnvelope, ...]

    def sensor(self, key: str) -> SensorEnvelope | None:
        return next((s for s in self.sensors if s.sensor_key == key), None)
