"""Pluggable forecast-model interface (ADR-017 §13).

Every forecast model - baselines now, NeuralProphet / LSTM / TCN / Transformer
later - implements this one interface, so new models plug in without touching
preprocessing, backtesting, selection, or projection. A model turns a 1-D
history into a mean path plus prediction intervals; it is deterministic given
its inputs (reproducibility).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from senseminds.forecasting.models import Forecast, z_score


class ForecastModel(ABC):
    """A univariate forecaster producing mean + prediction intervals."""

    name: str
    version: str
    # rough relative cost/complexity for tie-breaking in selection (lower simpler)
    cost: int = 1

    @abstractmethod
    def forecast(self, y: np.ndarray, horizon: int, season: int) -> Forecast:
        """Forecast ``horizon`` steps ahead from history ``y``."""

    @staticmethod
    def _interval(mean: np.ndarray, resid_std: float, per_step_growth: np.ndarray) -> Forecast:
        z = z_score()
        band = z * resid_std * per_step_growth
        return Forecast(
            mean=mean, lower=mean - band, upper=mean + band,
            horizon=len(mean), method="", model_version="",
        )
