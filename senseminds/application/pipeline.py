"""Deterministic analysis pipeline.

Runs the deterministic engine DAG for one unit in dependency order and returns
a populated `AnalysisContext`. This is the single place the wiring lives, so
tests and consumers stop re-wiring engines by hand (ADR-011 finding 2.4). Order
encodes the real dependencies:

    Statistics ─┐
    State ──────┤
                ├─▶ Envelope(Statistics) ─▶ Threshold(Envelope) ─▶ Timeline(State, Threshold)
"""

from __future__ import annotations

from senseminds.application.context import AnalysisContext
from senseminds.engines.operating_envelope import OperatingEnvelopeEngine
from senseminds.engines.operating_state import OperatingStateEngine
from senseminds.engines.operational_timeline import OperationalTimelineEngine
from senseminds.engines.quality import QualityGate
from senseminds.engines.reliability import ReliabilityEngine
from senseminds.engines.statistics import StatisticsEngine
from senseminds.engines.threshold import ThresholdEngine
from senseminds.ingestion import IngestedSeries


class DeterministicPipeline:
    """Run the deterministic analytics DAG for a unit."""

    def __init__(self) -> None:
        self._quality = QualityGate()
        self._statistics = StatisticsEngine()
        self._state = OperatingStateEngine()
        self._envelope = OperatingEnvelopeEngine()
        self._threshold = ThresholdEngine()
        self._timeline = OperationalTimelineEngine()
        self._reliability = ReliabilityEngine()

    def run(self, series: IngestedSeries) -> AnalysisContext:
        quality = self._quality.evaluate(series)
        statistics = self._statistics.compute(series)
        operating_state = self._state.compute(series)
        envelope = self._envelope.compute(series, statistics)
        threshold = self._threshold.compute(series, envelope)
        timeline = self._timeline.compute(operating_state, threshold)
        reliability = self._reliability.compute(series, quality, statistics)
        return AnalysisContext(
            unit=series.manifest.unit,
            series=series,
            quality=quality,
            statistics=statistics,
            operating_state=operating_state,
            envelope=envelope,
            threshold=threshold,
            timeline=timeline,
            reliability=reliability,
        )
