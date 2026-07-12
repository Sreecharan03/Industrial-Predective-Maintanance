"""Operating Envelope engine.

Refactor of Phase-2 ``step8`` into a typed, reusable engine. It CONSUMES the
Statistics engine's output for all percentile/spread values (no duplicated
computation - the dependency rule) and computes only the envelope-specific
mode band and rare region from the validated readings. Output matches Phase-2
exactly (tests/test_parity_operating_envelope.py).

Algorithm details (histogram binning) live only in this module; the public
result models expose domain concepts, not the method.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from senseminds.domain.value_objects import Confidence
from senseminds.engines.base import BaseEngine
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.operating_envelope.models import (
    Band,
    EnvelopeBands,
    EnvelopeEvidence,
    ModeBand,
    OperatingEnvelopeResult,
    RareRegion,
    SensorEnvelope,
)
from senseminds.engines.statistics.models import SensorStatistics, StatisticsResult
from senseminds.ingestion.models import IngestedSeries

_MIN_POINTS = 30
_MIN_STD = 1e-9


class OperatingEnvelopeEngine(BaseEngine):
    """Derive each sensor's operating envelope from history + statistics.

    Bins and the rare-region fraction are engine tuning knobs (not deployment
    config), injectable with Phase-2 defaults for reproducibility/testing.
    """

    name = "operating_envelope"
    version = "0.1.0"

    def __init__(self, bins: int = 40, rare_fraction: float = 0.01) -> None:
        if bins < 1:
            raise ValueError("bins must be >= 1")
        if not 0.0 < rare_fraction < 1.0:
            raise ValueError("rare_fraction must be in (0, 1)")
        self._bins = bins
        self._rare_fraction = rare_fraction

    # --- internal: the only place histogram logic exists ---
    def _mode_band(self, series: pd.Series) -> ModeBand | None:
        s = series.dropna()
        if len(s) < _MIN_POINTS or s.std() < _MIN_STD:
            return None
        counts, edges = np.histogram(s, bins=self._bins)
        top = int(counts.argmax())
        share = counts[top] / counts.sum()
        return ModeBand(
            low=float(edges[top]), high=float(edges[top + 1]), share_pct=round(100 * share, 2)
        )

    def _rare_region(self, series: pd.Series) -> RareRegion | None:
        s = series.dropna()
        if len(s) < _MIN_POINTS or s.std() < _MIN_STD:
            return None
        counts, edges = np.histogram(s, bins=self._bins)
        total = counts.sum()
        rare_idx = np.where(counts / total < self._rare_fraction)[0]
        if len(rare_idx) == 0:
            return None
        rare_pct = round(100 * counts[rare_idx].sum() / total, 2)
        low_end = float(edges[rare_idx.min() + 1]) if rare_idx.min() == 0 else None
        high_start = float(edges[rare_idx.max()]) if rare_idx.max() == len(counts) - 1 else None
        return RareRegion(low_end=low_end, high_start=high_start, pct_of_readings=rare_pct)

    def _bands(self, stat: SensorStatistics, series: pd.Series) -> EnvelopeBands:
        return EnvelopeBands(
            normal_window=Band(low=stat.p5, high=stat.p95),
            typical_range=Band(low=stat.p25, high=stat.p75),
            median=stat.median,
            iqr=stat.iqr,
            cv_pct=stat.cv_pct,
            mode_band=self._mode_band(series),
            rare_region=self._rare_region(series),
        )

    def _evidence(
        self, stat: SensorStatistics, n_rows: int, bands: EnvelopeBands
    ) -> EnvelopeEvidence:
        coverage = round(100 * stat.count / n_rows, 2) if n_rows else 0.0
        conf_value = max(0.0, min(1.0, 1 - stat.missing_pct / 100))
        limitations: list[str] = []
        if stat.count == 0:
            limitations.append("No valid readings; envelope is undefined for this sensor.")
        elif bands.mode_band is None:
            limitations.append(
                "Distribution too sparse or flat for a most-frequent band; percentile window only."
            )
        else:
            limitations.append(
                "The most-frequent band reflects the single densest region; a multimodal sensor "
                "may have additional peaks not represented by it."
            )
        if coverage < 90:
            limitations.append(
                f"Data coverage is {coverage}% - envelope based on a partial history."
            )
        return EnvelopeEvidence(
            sample_count=stat.count,
            coverage_pct=coverage,
            missing_pct=stat.missing_pct,
            confidence=Confidence(
                value=conf_value,
                rationale=f"{coverage}% coverage ({stat.count} of {n_rows} readings valid).",
            ),
            assumptions=(
                "A single engineering unit applies across the analysed window (per catalog).",
                "Readings represent normal historical operation, not a controlled test.",
            ),
            limitations=tuple(limitations),
        )

    def compute(
        self, series: IngestedSeries, statistics: StatisticsResult
    ) -> OperatingEnvelopeResult:
        unit = series.manifest.unit
        if statistics.unit != unit:
            raise EngineInputError(
                f"statistics unit {statistics.unit!r} does not match series unit {unit!r}"
            )
        n_rows = series.manifest.n_rows
        sensors: list[SensorEnvelope] = []
        for key in series.manifest.sensor_keys:
            stat = statistics.sensor(key)
            if stat is None:
                raise EngineInputError(f"statistics has no entry for sensor {key!r}")
            bands = self._bands(stat, series.frame[key])
            sensors.append(
                SensorEnvelope(
                    sensor_key=key,
                    bands=bands,
                    evidence=self._evidence(stat, n_rows, bands),
                )
            )
        self.log.info("operating_envelope_computed", extra={"unit": unit, "sensors": len(sensors)})
        return OperatingEnvelopeResult(
            artifact_id=f"{unit}__operating_envelope",
            provenance=self.provenance_from_frame(unit, series.frame),
            unit=unit,
            window_start=series.manifest.start,
            window_end=series.manifest.end,
            sensors=tuple(sensors),
        )
