"""Gap-aware forecast preprocessing (ADR-017 §2).

Resamples a sensor to a regular grid and returns only the **most recent
contiguous, sufficiently-covered segment** as the forecast origin - so a model
never forecasts across or out of a multi-week gap. Deterministic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from senseminds.forecasting.models import ForecastInput
from senseminds.ingestion.models import IngestedSeries


class ForecastPreprocessor:
    """Build a gap-free regular-cadence forecast input for a sensor."""

    def __init__(self, freq: str = "1h", season: int = 24, min_history: int = 72) -> None:
        self._freq = freq
        self._season = season
        self._min_history = min_history

    def prepare(self, series: IngestedSeries, sensor_key: str) -> ForecastInput | None:
        frame = series.frame[["timestamp", sensor_key]].dropna()
        if frame.empty:
            return None
        s = (
            frame.set_index("timestamp")[sensor_key]
            .resample(self._freq)
            .mean()
        )
        # most-recent contiguous (non-NaN) run
        trailing = self._trailing_contiguous(s)
        if trailing is None or len(trailing) < max(self._min_history, 2 * self._season):
            return None
        return ForecastInput(
            unit=series.manifest.unit,
            sensor_key=sensor_key,
            y=trailing.to_numpy(dtype=float),
            season=self._season,
            step=pd.Timedelta(self._freq).to_pytimedelta(),
            origin_time=trailing.index[-1].to_pydatetime(),
        )

    @staticmethod
    def _trailing_contiguous(s: pd.Series) -> pd.Series | None:
        mask = s.notna().to_numpy()
        if not mask.any():
            return None
        # walk back from the end while values are present
        end = len(mask)
        i = end - 1
        while i >= 0 and mask[i]:
            i -= 1
        start = i + 1
        return s.iloc[start:end] if end - start > 0 else None


def crosses(mean: np.ndarray, lower: np.ndarray, upper: np.ndarray,
            low: float | None, high: float | None) -> int | None:
    """First horizon step whose interval crosses an operating bound, else None."""
    for h in range(len(mean)):
        if high is not None and upper[h] > high:
            return h
        if low is not None and lower[h] < low:
            return h
    return None
