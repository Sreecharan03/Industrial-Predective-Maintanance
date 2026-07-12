"""Statistics engine.

Refactor of Phase-1 ``step4`` / ``common.compute_full_stats`` into a typed,
stateless service. Pure descriptive statistics computed directly from the
validated readings - no imputation, smoothing, or synthetic values, and no
model. Formulas match Phase-1 exactly so the output is provably identical
(see tests/test_parity_statistics.py).
"""

from __future__ import annotations

import pandas as pd

from senseminds.engines.base import BaseEngine
from senseminds.engines.statistics.models import SensorStatistics, StatisticsResult
from senseminds.ingestion.models import IngestedSeries


def _sensor_statistics(key: str, column: pd.Series, n_total: int) -> SensorStatistics:
    valid = column.dropna()
    n_valid = len(valid)
    n_missing = n_total - n_valid
    missing_pct = round(100 * n_missing / n_total, 2) if n_total else 0.0

    if n_valid == 0:
        return SensorStatistics(
            sensor_key=key, count=0, missing=n_missing, missing_pct=missing_pct, unique=0
        )

    p5, p25, p75, p95 = (float(valid.quantile(q)) for q in (0.05, 0.25, 0.75, 0.95))
    iqr = p75 - p25
    mean = float(valid.mean())
    std = float(valid.std())
    minimum, maximum = float(valid.min()), float(valid.max())

    cv_pct = 100 * std / mean if mean not in (0.0,) and not pd.isna(mean) else None

    lo, hi = p25 - 1.5 * iqr, p75 + 1.5 * iqr
    n_outliers = int(((valid < lo) | (valid > hi)).sum())

    return SensorStatistics(
        sensor_key=key,
        count=n_valid,
        missing=n_missing,
        missing_pct=missing_pct,
        unique=int(valid.nunique()),
        minimum=minimum,
        maximum=maximum,
        mean=mean,
        median=float(valid.median()),
        std=std,
        variance=float(valid.var()),
        p5=p5,
        p25=p25,
        p75=p75,
        p95=p95,
        iqr=iqr,
        value_range=maximum - minimum,
        cv_pct=cv_pct,
        iqr_outliers=n_outliers,
        iqr_outlier_pct=round(100 * n_outliers / n_valid, 2),
    )


class StatisticsEngine(BaseEngine):
    """Compute per-sensor engineering statistics for a unit."""

    name = "statistics"
    version = "0.1.0"

    def compute(self, series: IngestedSeries) -> StatisticsResult:
        frame = series.frame
        n_total = len(frame)
        sensors = tuple(
            _sensor_statistics(key, frame[key], n_total) for key in series.manifest.sensor_keys
        )
        self.log.info(
            "statistics_computed",
            extra={"unit": series.manifest.unit, "sensors": len(sensors)},
        )
        return StatisticsResult(
            artifact_id=f"{series.manifest.unit}__statistics",
            provenance=self.provenance_from_frame(series.manifest.unit, frame),
            unit=series.manifest.unit,
            n_rows=n_total,
            sensors=sensors,
        )
