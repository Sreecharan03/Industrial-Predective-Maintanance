"""Seasonal-naive baseline (ADR-017 §3).

Forecast = the value from one season ago, repeated. The honest baseline every
other model must beat. Intervals from the in-sample seasonal-difference residual,
widening slowly with horizon.
"""

from __future__ import annotations

import numpy as np

from senseminds.forecasting.base import ForecastModel
from senseminds.forecasting.models import Forecast, z_score


class SeasonalNaive(ForecastModel):
    name = "seasonal_naive"
    version = "0.1.0"
    cost = 0

    def forecast(self, y: np.ndarray, horizon: int, season: int) -> Forecast:
        season = max(1, min(season, len(y)))
        last_season = y[-season:]
        mean = np.array([last_season[h % season] for h in range(horizon)], dtype=float)
        resid = y[season:] - y[:-season] if len(y) > season else np.array([0.0])
        resid_std = float(np.std(resid)) if resid.size else 0.0
        growth = np.sqrt(1 + np.arange(horizon) // season)
        band = z_score() * resid_std * growth
        return Forecast(
            mean=mean, lower=mean - band, upper=mean + band,
            horizon=horizon, method=self.name, model_version=self.version,
        )
