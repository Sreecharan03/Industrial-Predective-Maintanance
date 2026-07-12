"""Additive Holt-Winters (ETS) baseline (ADR-017 §3).

Hand-rolled additive triple exponential smoothing (level + trend + seasonal) -
deterministic, explainable, dependency-light. Fixed smoothing parameters keep it
reproducible; intervals come from in-sample one-step residuals, widening with
the square root of the horizon.
"""

from __future__ import annotations

import numpy as np

from senseminds.forecasting.base import ForecastModel
from senseminds.forecasting.models import Forecast, z_score


class HoltWintersAdditive(ForecastModel):
    name = "holt_winters_additive"
    version = "0.1.0"
    cost = 1

    def __init__(self, alpha: float = 0.3, beta: float = 0.1, gamma: float = 0.1) -> None:
        self._alpha, self._beta, self._gamma = alpha, beta, gamma

    def forecast(self, y: np.ndarray, horizon: int, season: int) -> Forecast:
        m = max(2, min(season, len(y) // 2))
        level = float(np.mean(y[:m]))
        trend = float((np.mean(y[m : 2 * m]) - np.mean(y[:m])) / m)
        seasonal = [float(y[i] - level) for i in range(m)]

        fitted: list[float] = []
        for t in range(len(y)):
            s = seasonal[t % m]
            fitted.append(level + trend + s)
            prev_level = level
            level = self._alpha * (y[t] - s) + (1 - self._alpha) * (level + trend)
            trend = self._beta * (level - prev_level) + (1 - self._beta) * trend
            seasonal[t % m] = self._gamma * (y[t] - level) + (1 - self._gamma) * s

        mean = np.array(
            [level + (h + 1) * trend + seasonal[(len(y) + h) % m] for h in range(horizon)],
            dtype=float,
        )
        resid = y - np.array(fitted)
        resid_std = float(np.std(resid)) if resid.size else 0.0
        band = z_score() * resid_std * np.sqrt(np.arange(1, horizon + 1))
        return Forecast(
            mean=mean, lower=mean - band, upper=mean + band,
            horizon=horizon, method=self.name, model_version=self.version,
        )
