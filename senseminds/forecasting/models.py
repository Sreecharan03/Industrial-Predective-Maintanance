"""Forecasting models (ADR-017). All outputs are LEARNED hypotheses.

`ForecastInput` is the gap-aware, regular-cadence history a model forecasts from;
`Forecast` is a mean path with prediction intervals; `BacktestScore` is the
objective, walk-forward evidence used to *select* the production model per sensor
(the beat-the-baseline principle). Forecasting never decides breaches - it only
projects values with uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from pydantic import Field

from senseminds.domain.base import FrozenModel

INTERVAL_LEVEL = 0.8  # 80% prediction interval
_Z_80 = 1.2815515594


@dataclass(frozen=True)
class ForecastInput:
    """Regular-cadence, gap-free trailing history for one sensor."""

    unit: str
    sensor_key: str
    y: np.ndarray  # 1-D, most-recent contiguous segment
    season: int
    step: timedelta
    origin_time: datetime


@dataclass(frozen=True)
class Forecast:
    """A mean path with prediction intervals over the horizon."""

    mean: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    horizon: int
    method: str
    model_version: str


class BacktestScore(FrozenModel):
    """Objective walk-forward accuracy - the basis for model selection."""

    model: str
    mae: float = Field(ge=0.0)
    rmse: float = Field(ge=0.0)
    mape: float = Field(ge=0.0)
    coverage: float = Field(ge=0.0, le=1.0, description="Fraction of actuals inside the interval.")
    n_folds: int = Field(ge=0)


def z_score() -> float:
    return _Z_80
