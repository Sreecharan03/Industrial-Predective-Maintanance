"""Forecasting (Phase B, Increment 2) - label-free predictive-trend hypotheses.

Pluggable models selected per sensor by walk-forward backtesting; outputs are
LEARNED hypotheses, isolated from deterministic analytics (ADR-017).
"""

from senseminds.forecasting.backtest import walk_forward
from senseminds.forecasting.base import ForecastModel
from senseminds.forecasting.ets import HoltWintersAdditive
from senseminds.forecasting.forecaster import Forecaster
from senseminds.forecasting.models import (
    BacktestScore,
    Forecast,
    ForecastInput,
)
from senseminds.forecasting.preprocessing import ForecastPreprocessor
from senseminds.forecasting.seasonal_naive import SeasonalNaive
from senseminds.forecasting.selection import ModelSelector

__all__ = [
    "BacktestScore",
    "Forecast",
    "ForecastInput",
    "ForecastModel",
    "ForecastPreprocessor",
    "Forecaster",
    "HoltWintersAdditive",
    "ModelSelector",
    "SeasonalNaive",
    "walk_forward",
]
