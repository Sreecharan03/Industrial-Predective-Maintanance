"""Deterministic feature pipeline (ADR-016 §4).

Builds engineered per-window feature vectors from the *validated* series - never
raw ticks. Windows are fixed-size consecutive reading chunks; each feature is a
per-window sensor mean, z-normalised over history for scale-free comparison, and
optionally reliability-weighted so untrustworthy sensors contribute less. Fully
deterministic: same series (+ reliability) -> identical FeatureFrame.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from senseminds.ingestion.models import IngestedSeries
from senseminds.pattern_learning.models import FeatureFrame

_MIN_COVERAGE_FRACTION = 0.5  # a window needs >=50% populated to count as covered


class FeaturePipeline:
    """Turn a validated series into engineered per-window features."""

    def __init__(self, window_size: int = 48) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        self._window_size = window_size

    def build(
        self, series: IngestedSeries, reliability: Mapping[str, float] | None = None
    ) -> FeatureFrame:
        frame = series.frame.sort_values("timestamp").reset_index(drop=True)
        keys = list(series.manifest.sensor_keys)
        n = len(frame)
        w = self._window_size
        n_windows = max(n // w, 0)

        rows: list[np.ndarray] = []
        starts: list = []
        ends: list = []
        counts: list[int] = []
        covered = 0
        for i in range(n_windows):
            chunk = frame.iloc[i * w : (i + 1) * w]
            means = [chunk[k].mean() for k in keys]  # NaN if fully empty
            rows.append(np.array(means, dtype=float))
            starts.append(pd.Timestamp(chunk["timestamp"].iloc[0]).to_pydatetime())
            ends.append(pd.Timestamp(chunk["timestamp"].iloc[-1]).to_pydatetime())
            populated = int(chunk[keys].notna().any(axis=1).sum())
            counts.append(populated)
            if populated >= _MIN_COVERAGE_FRACTION * w:
                covered += 1

        matrix = np.vstack(rows) if rows else np.empty((0, len(keys)))
        matrix = self._normalise(matrix)
        if reliability:
            weights = np.array([reliability.get(k, 1.0) for k in keys], dtype=float)
            matrix = matrix * weights
        coverage_pct = round(100 * covered / n_windows, 2) if n_windows else 0.0

        return FeatureFrame(
            unit=series.manifest.unit,
            matrix=matrix,
            feature_names=tuple(keys),
            window_starts=tuple(starts),
            window_ends=tuple(ends),
            n_readings=tuple(counts),
            coverage_pct=coverage_pct,
        )

    @staticmethod
    def _normalise(matrix: np.ndarray) -> np.ndarray:
        """Column z-normalise; NaN -> 0 (the column mean after centring)."""
        if matrix.size == 0:
            return matrix
        mean = np.nanmean(matrix, axis=0)
        std = np.nanstd(matrix, axis=0)
        std = np.where(std < 1e-9, 1.0, std)
        z = (matrix - mean) / std
        return np.nan_to_num(z, nan=0.0)
