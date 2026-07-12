"""Walk-forward backtesting (ADR-017 §8).

Because a forecast's target is observed, models are scored objectively on
held-out actuals: MAE / RMSE / MAPE + prediction-interval coverage. This is the
evidence the ModelSelector uses to pick the production model per sensor.
"""

from __future__ import annotations

import numpy as np

from senseminds.forecasting.base import ForecastModel
from senseminds.forecasting.models import BacktestScore

_NO_SCORE = 1e9


def walk_forward(
    model: ForecastModel, y: np.ndarray, horizon: int, season: int, n_folds: int = 3
) -> BacktestScore:
    abs_err: list[float] = []
    sq_err: list[float] = []
    pct_err: list[float] = []
    covered = 0
    total = 0
    used = 0
    for k in range(n_folds):
        cut = len(y) - (n_folds - k) * horizon
        if cut < 2 * season:
            continue
        train, actual = y[:cut], y[cut : cut + horizon]
        if actual.size == 0:
            continue
        fc = model.forecast(train, actual.size, season)
        mean, lo, up = fc.mean[: actual.size], fc.lower[: actual.size], fc.upper[: actual.size]
        abs_err.extend(np.abs(mean - actual))
        sq_err.extend((mean - actual) ** 2)
        denom = np.where(np.abs(actual) < 1e-9, 1e-9, np.abs(actual))
        pct_err.extend(np.abs((mean - actual) / denom))
        covered += int(((actual >= lo) & (actual <= up)).sum())
        total += actual.size
        used += 1

    if not abs_err:
        return BacktestScore(model=model.name, mae=_NO_SCORE, rmse=_NO_SCORE, mape=_NO_SCORE,
                             coverage=0.0, n_folds=0)
    return BacktestScore(
        model=model.name,
        mae=round(float(np.mean(abs_err)), 6),
        rmse=round(float(np.sqrt(np.mean(sq_err))), 6),
        mape=round(float(np.mean(pct_err) * 100), 4),
        coverage=round(covered / total, 4),
        n_folds=used,
    )
