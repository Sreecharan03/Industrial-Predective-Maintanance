"""Forecaster orchestrator (ADR-017).

Per sensor: gap-aware preprocess -> backtest-select a model -> forecast with
intervals -> if the interval crosses a threshold *definition* within the horizon,
emit a LEARNED FORECAST_THRESHOLD_APPROACH hypothesis (lead time + interval +
model + backtest score). Reads threshold *definitions* only; never calls the
Threshold engine, never changes any deterministic verdict. Returns a
`PatternResult` so the existing PatternProjector folds it into the graph.
"""

from __future__ import annotations

from collections.abc import Sequence

from senseminds.catalog import thresholds_for
from senseminds.domain.entities import Asset
from senseminds.domain.enums import Severity, ThresholdStatus
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
    ObservedWindow,
)
from senseminds.findings.identity import finding_id, identity_key
from senseminds.forecasting.base import ForecastModel
from senseminds.forecasting.ets import HoltWintersAdditive
from senseminds.forecasting.models import Forecast, ForecastInput
from senseminds.forecasting.preprocessing import ForecastPreprocessor, crosses
from senseminds.forecasting.seasonal_naive import SeasonalNaive
from senseminds.forecasting.selection import ModelSelector
from senseminds.ingestion.models import IngestedSeries
from senseminds.pattern_learning.base import matrix_hash, now_utc
from senseminds.pattern_learning.models import (
    DiscoveredPattern,
    ModelHealth,
    PatternLifecycle,
    PatternResult,
)


class Forecaster:
    """Backtest-selected, interval forecasting emitting LEARNED hypotheses."""

    model_id = "forecaster"
    version = "0.1.0"

    def __init__(
        self,
        horizon: int = 24,
        freq: str = "1h",
        season: int = 24,
        margin: float = 0.05,
        n_folds: int = 3,
        baseline: ForecastModel | None = None,
        candidates: Sequence[ForecastModel] | None = None,
    ) -> None:
        self._horizon = horizon
        self._season = season
        self._pre = ForecastPreprocessor(freq, season, min_history=max(72, 3 * season))
        self._selector = ModelSelector(
            baseline or SeasonalNaive(), candidates or (HoltWintersAdditive(),), margin, n_folds
        )

    def forecast_unit(
        self, series: IngestedSeries, asset: Asset, sensor_keys: Sequence[str] | None = None
    ) -> PatternResult:
        unit = series.manifest.unit
        thresholds = thresholds_for(unit, asset)
        subsystem_of = {k: sub.key for sub in asset.subsystems for k in sub.sensor_keys}
        keys = list(sensor_keys) if sensor_keys is not None else [
            k for k, t in thresholds.items() if t.status is ThresholdStatus.AVAILABLE
        ]

        findings: list[Finding] = []
        patterns: list[DiscoveredPattern] = []
        n_forecast = 0
        interval_coverages: list[float] = []
        for key in keys:
            inp = self._pre.prepare(series, key)
            if inp is None:
                continue
            n_forecast += 1
            model, scores = self._selector.select(inp.y, self._horizon, self._season)
            fc = model.forecast(inp.y, self._horizon, self._season)
            score = scores[model.name]
            interval_coverages.append(score.coverage)

            patterns.append(
                DiscoveredPattern(
                    pattern_id=f"forecast:{unit}:{key}", model_id=self.model_id,
                    model_version=self.version, kind="forecast",
                    label=f"{key} forecast via {model.name}", support_windows=self._horizon,
                    confidence=round(score.coverage, 4), lifecycle=PatternLifecycle.STABLE,
                    descriptor={"method": model.name, "mae": score.mae, "coverage": score.coverage},
                )
            )

            band = thresholds.get(key)
            low = band.minimum if band else None
            high = band.maximum if band else None
            h = crosses(fc.mean, fc.lower, fc.upper, low, high)
            if h is not None:
                bound = high if (high is not None and fc.upper[h] > high) else low
                findings.append(
                    self._approach(inp, key, model, fc, h, bound, score, subsystem_of.get(key))
                )

        coverage_pct = round(100 * n_forecast / len(keys), 2) if keys else 0.0
        mean_cov = (
            round(sum(interval_coverages) / len(interval_coverages), 4)
            if interval_coverages
            else 0.0
        )
        health = ModelHealth(
            coverage_pct=coverage_pct, feature_completeness_pct=100.0 if keys else 0.0,
            drift_indicator=0.0, reproducible=True,
            note=f"walk-forward backtested; mean interval coverage {mean_cov}",
        )
        return PatternResult(
            unit=unit, model_id=self.model_id, model_version=self.version,
            findings=tuple(findings), patterns=tuple(patterns), model_health=health,
        )

    def _approach(
        self, inp: ForecastInput, key: str, model: ForecastModel, fc: Forecast,
        h: int, bound: float | None, score, subsystem_key: str | None,  # noqa: ANN001
    ) -> Finding:
        unit = inp.unit
        idk = identity_key(unit, FindingType.FORECAST_THRESHOLD_APPROACH, FindingScope.SENSOR, key)
        input_hash = matrix_hash(inp.y)
        model_ref = f"forecast:{model.name}@{model.version}"
        lead_steps = h + 1
        lead_hours = round(lead_steps * inp.step.total_seconds() / 3600, 1)
        evidence = (
            Evidence(artifact_id=model_ref, description="forecast mean at crossing",
                     observed_value=round(float(fc.mean[h]), 3)),
            Evidence(artifact_id=model_ref, description="operating bound approached",
                     observed_value=bound),
            Evidence(artifact_id=model_ref, description="lead-time steps to crossing",
                     observed_value=lead_steps),
            Evidence(artifact_id=model_ref, description="backtest MAE", observed_value=score.mae),
        )
        end = inp.origin_time + inp.step * self._horizon
        return Finding(
            finding_id=finding_id(idk, input_hash), identity_key=idk,
            finding_type=FindingType.FORECAST_THRESHOLD_APPROACH, category=FindingCategory.ANOMALY,
            scope=FindingScope.SENSOR, origin=FindingOrigin.LEARNED,
            summary=(
                f"{key} projected to approach its operating limit in ~{lead_hours}h "
                "(hypothesis)"
            ),
            detail=f"{model.name} forecast interval crosses {bound} at ~step {lead_steps} "
            f"(~{lead_hours}h ahead); 80% interval. Advisory, not a breach.",
            target_key=key, equipment_key=unit, subsystem_key=subsystem_key, severity=Severity.INFO,
            confidence=Confidence(
                value=round(max(0.0, min(1.0, score.coverage)), 4),
                rationale=f"interval coverage {score.coverage}, MAE {score.mae}",
            ),
            evidence=evidence, source_engine=model_ref,
            observed_window=ObservedWindow(start=inp.origin_time, end=end),
            provenance=Provenance(
                engine="forecasting", engine_version=self.version, source_unit=unit,
                input_hash=input_hash, produced_at=now_utc(),
            ),
        )
