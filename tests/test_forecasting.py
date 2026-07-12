"""Forecasting (Phase B, Increment 2) - behaviour, backtest-selection,
reproducibility, threshold-approach hypotheses, boundary isolation, KG."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from senseminds.findings import FindingCategory, FindingOrigin, FindingType
from senseminds.forecasting import (
    Forecaster,
    ForecastPreprocessor,
    HoltWintersAdditive,
    ModelSelector,
    SeasonalNaive,
    walk_forward,
)
from senseminds.ingestion import ProcessedCsvSource
from senseminds.knowledge_graph import InMemoryKnowledgeGraph, NodeType
from senseminds.pattern_learning import PatternProjector


def _series(tmp_path: Path, values: dict[str, list], start: str = "2024-01-01"):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range(start, periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    return ProcessedCsvSource(tmp_path).load("SC-126")


# ----------------------------- preprocessing --------------------------

def test_preprocessing_takes_trailing_contiguous(tmp_path: Path) -> None:
    # 5 days, a big gap, then 5 days -> only the recent 5 days survive
    a = pd.date_range("2024-01-01", periods=240, freq="30min")
    b = pd.date_range("2024-03-01", periods=240, freq="30min")
    ts = list(a) + list(b)
    vals = list(240.0 + np.zeros(480))
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], "Discharge Pressure": vals}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    inp = ForecastPreprocessor(freq="1h", season=24).prepare(series, "discharge_pressure")
    assert inp is not None
    assert 100 <= len(inp.y) <= 130  # ~5 days hourly, not the full 10


# ----------------------------- baselines ------------------------------

def test_models_produce_intervals(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Discharge Pressure": list(240 + np.sin(np.linspace(0, 40, 960)))})
    inp = ForecastPreprocessor().prepare(series, "discharge_pressure")
    for model in (SeasonalNaive(), HoltWintersAdditive()):
        fc = model.forecast(inp.y, 24, 24)
        assert fc.mean.shape == (24,)
        assert np.all(fc.lower <= fc.mean) and np.all(fc.mean <= fc.upper)


# ----------------------------- backtest + selection -------------------

def test_backtest_scores(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Discharge Pressure": list(np.linspace(230, 246, 960))})
    inp = ForecastPreprocessor().prepare(series, "discharge_pressure")
    score = walk_forward(SeasonalNaive(), inp.y, 24, 24, n_folds=3)
    assert score.n_folds > 0 and score.mae >= 0


def test_selector_promotes_ets_on_trend(tmp_path: Path) -> None:
    # a strong linear trend: ETS (captures trend) must beat seasonal-naive.
    series = _series(tmp_path, {"Discharge Pressure": list(np.linspace(200, 246, 960))})
    inp = ForecastPreprocessor().prepare(series, "discharge_pressure")
    chosen, scores = ModelSelector(SeasonalNaive(), (HoltWintersAdditive(),)).select(inp.y, 24, 24)
    assert chosen.name == "holt_winters_additive"
    assert scores["holt_winters_additive"].mae < scores["seasonal_naive"].mae


# ----------------------------- reproducibility ------------------------

def test_forecaster_is_reproducible(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Discharge Pressure": list(np.linspace(230, 246, 960))})
    a = Forecaster().forecast_unit(series, series.asset, sensor_keys=["discharge_pressure"])
    b = Forecaster().forecast_unit(series, series.asset, sensor_keys=["discharge_pressure"])
    assert [f.finding_id for f in a.findings] == [f.finding_id for f in b.findings]


# ----------------------------- threshold approach ---------------------

def test_rising_sensor_yields_threshold_approach(tmp_path: Path) -> None:
    # rising toward the 235-247 discharge-pressure band -> approach hypothesis
    series = _series(tmp_path, {"Discharge Pressure": list(np.linspace(230, 246, 960))})
    result = Forecaster().forecast_unit(series, series.asset, sensor_keys=["discharge_pressure"])
    approaches = [
        f for f in result.findings if f.finding_type is FindingType.FORECAST_THRESHOLD_APPROACH
    ]
    assert approaches
    f = approaches[0]
    assert f.origin is FindingOrigin.LEARNED
    assert "hypothesis" in f.summary.lower()


def test_stable_sensor_yields_no_approach(tmp_path: Path) -> None:
    vals = list(240 + np.random.default_rng(0).normal(0, 0.2, 960))
    series = _series(tmp_path, {"Discharge Pressure": vals})
    result = Forecaster().forecast_unit(series, series.asset, sensor_keys=["discharge_pressure"])
    assert not any(
        f.finding_type is FindingType.FORECAST_THRESHOLD_APPROACH for f in result.findings
    )
    assert result.patterns  # still produces a forecast pattern


# ----------------------------- boundary isolation ---------------------

def test_forecasts_are_learned_hypotheses(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Discharge Pressure": list(np.linspace(230, 246, 960))})
    result = Forecaster().forecast_unit(series, series.asset, sensor_keys=["discharge_pressure"])
    for f in result.findings:
        assert f.origin is FindingOrigin.LEARNED
        assert f.category is FindingCategory.ANOMALY
        assert f.provenance.engine == "forecasting"
    assert result.model_health.reproducible is True


# ----------------------------- KG projection --------------------------

def test_forecast_hypotheses_project_to_graph(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Discharge Pressure": list(np.linspace(230, 246, 960))})
    result = Forecaster().forecast_unit(series, series.asset, sensor_keys=["discharge_pressure"])
    repo = InMemoryKnowledgeGraph()
    proj = PatternProjector(repo)
    proj.project(result)
    proj.project(result)  # idempotent
    patterns = repo.nodes(NodeType.DISCOVERED_PATTERN)
    assert patterns
    assert all(p.properties["status"] == "hypothesis" for p in patterns)
    assert repo.nodes(NodeType.LEARNED_MODEL)
