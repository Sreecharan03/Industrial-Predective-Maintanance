"""AnalysisContext - the per-unit bundle of engine results.

Fan-in consumers (Health, and later Rules) grow unwieldy positional signatures
if they take five separate results. `AnalysisContext` bundles them into one
typed container so those engines take a single argument while still declaring
their real dependencies explicitly: each consumer calls `require(...)` for the
results it needs, which fails loudly if the pipeline has not produced them yet
(ADR-011 finding 2.4). It is a frozen dataclass, not a Pydantic model, because
it carries the pandas-backed `IngestedSeries` across the boundary.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from senseminds.engines.operating_envelope import OperatingEnvelopeResult
from senseminds.engines.operating_state import OperatingStateResult
from senseminds.engines.operational_timeline import OperationalTimelineResult
from senseminds.engines.quality import QualityResult
from senseminds.engines.reliability import ReliabilityResult
from senseminds.engines.statistics import StatisticsResult
from senseminds.engines.threshold import ThresholdResult
from senseminds.ingestion import IngestedSeries


class MissingDependencyError(RuntimeError):
    """A consumer required an engine result the context does not yet hold."""


@dataclass(frozen=True)
class AnalysisContext:
    """All engine results produced for one unit, populated by the pipeline."""

    unit: str
    series: IngestedSeries
    quality: QualityResult | None = None
    statistics: StatisticsResult | None = None
    operating_state: OperatingStateResult | None = None
    envelope: OperatingEnvelopeResult | None = None
    threshold: ThresholdResult | None = None
    timeline: OperationalTimelineResult | None = None
    reliability: ReliabilityResult | None = None

    def require(self, *names: str) -> None:
        """Assert the named result fields are present; raise if any is missing."""
        missing = [n for n in names if getattr(self, n, None) is None]
        if missing:
            raise MissingDependencyError(
                f"AnalysisContext for {self.unit!r} is missing required result(s): "
                f"{', '.join(missing)}"
            )

    def with_results(self, **results: object) -> AnalysisContext:
        """Return a copy with additional result fields populated."""
        return dataclasses.replace(self, **results)
