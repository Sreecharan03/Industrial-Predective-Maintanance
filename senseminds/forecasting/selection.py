"""Backtest-driven model selection (ADR-017 §13).

Chooses the production model **per sensor** purely from walk-forward backtest
evidence. Guiding principle, enforced here: **no model earns a production slot
unless it beats the simpler baseline by a margin.** The selector defaults to the
baseline and only promotes a more complex model when the data justifies it -
ties broken by lower cost then name (deterministic).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from senseminds.forecasting.backtest import walk_forward
from senseminds.forecasting.base import ForecastModel
from senseminds.forecasting.models import BacktestScore


class ModelSelector:
    """Select the best forecast model for a series via backtesting."""

    def __init__(
        self,
        baseline: ForecastModel,
        candidates: Sequence[ForecastModel],
        margin: float = 0.05,
        n_folds: int = 3,
    ) -> None:
        self._baseline = baseline
        self._candidates = tuple(candidates)
        self._margin = margin
        self._n_folds = n_folds

    def select(
        self, y: np.ndarray, horizon: int, season: int
    ) -> tuple[ForecastModel, dict[str, BacktestScore]]:
        base_score = walk_forward(self._baseline, y, horizon, season, self._n_folds)
        scores = {self._baseline.name: base_score}
        best, best_score = self._baseline, base_score
        for c in self._candidates:
            sc = walk_forward(c, y, horizon, season, self._n_folds)
            scores[c.name] = sc
            # a candidate must beat the baseline by the margin to earn its place,
            # then win on (mae, cost, name) among qualifying candidates
            beats_baseline = sc.mae < base_score.mae * (1 - self._margin)
            better_than_best = best is self._baseline or (sc.mae, c.cost, c.name) < (
                best_score.mae, best.cost, best.name
            )
            if beats_baseline and better_than_best:
                best, best_score = c, sc
        return best, scores
