"""Quality gate engine.

Refactors the Phase-1 inspection/data-quality rule checks (physical validity,
fault-code patterns, logging gaps) into a stateless engine that emits a typed
`QualityResult`. Sensor rules are dispatched on the catalog `SensorType`, not
on column-name string matching, so a renamed column can never silently escape
its check. Deterministic; no anomaly model.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from senseminds.domain.enums import SensorType
from senseminds.domain.value_objects import Provenance
from senseminds.engines.quality.models import QualityResult, SensorQuality
from senseminds.ingestion.models import IngestedSeries

ENGINE_NAME = "quality"
ENGINE_VERSION = "0.1.0"

# Sensor types for which a negative reading is physically invalid.
_NON_NEGATIVE_TYPES = {SensorType.PRESSURE, SensorType.ELECTRICAL_CURRENT, SensorType.FLOW}
# Sensor types constrained to a 0-100 percentage range.
_PERCENT_TYPES = {SensorType.LOAD, SensorType.GAS_PURITY}


def _fault_code(series: pd.Series) -> tuple[float | None, int]:
    """Phase-1 rule: a single non-zero value repeating far more than chance and
    sitting >4 IQR from the median - a likely disconnected-transducer code."""
    s = series.dropna()
    if len(s) < 100:
        return None, 0
    counts = s.value_counts()
    top_val, top_count = float(counts.index[0]), int(counts.iloc[0])
    if top_val == 0:  # legitimate off/idle floor, not a fault code
        return None, 0
    if top_count < max(30, 0.003 * len(s)):
        return None, 0
    iqr = s.quantile(0.75) - s.quantile(0.25)
    if iqr == 0:
        return None, 0
    if abs(top_val - s.median()) / iqr > 4:
        return top_val, top_count
    return None, 0


def _longest_flatline(series: pd.Series) -> int:
    s = series.dropna().reset_index(drop=True)
    if len(s) < 2:
        return len(s)
    run_id = (s != s.shift()).cumsum()
    return int(s.groupby(run_id).transform("size").max())


def _input_hash(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=False).values.tobytes()
    )
    return digest.hexdigest()[:16]


class QualityGate:
    """Evaluate a unit's ingested series into a typed QualityResult."""

    def __init__(self, gap_threshold_hours: float = 4.0) -> None:
        self._gap_hours = gap_threshold_hours

    def evaluate(self, series: IngestedSeries) -> QualityResult:
        frame = series.frame
        asset = series.asset
        n_rows = len(frame)
        sensor_type = {s.key: s.sensor_type for s in asset.sensors}

        sensors: list[SensorQuality] = []
        empty_columns: list[str] = []
        for key in series.manifest.sensor_keys:
            col = frame[key]
            valid = col.dropna()
            n_missing = int(col.isna().sum())
            if len(valid) == 0:
                empty_columns.append(key)
            stype = sensor_type[key]
            n_negative = int((valid < 0).sum()) if stype in _NON_NEGATIVE_TYPES else 0
            n_out_of_range = (
                int(((valid < 0) | (valid > 100)).sum()) if stype in _PERCENT_TYPES else 0
            )
            fault_val, fault_count = _fault_code(col)
            sensors.append(
                SensorQuality(
                    sensor_key=key,
                    n_valid=len(valid),
                    n_missing=n_missing,
                    missing_pct=round(100 * n_missing / n_rows, 4) if n_rows else 0.0,
                    n_negative=n_negative,
                    n_out_of_range=n_out_of_range,
                    fault_code_value=fault_val,
                    fault_code_count=fault_count,
                    longest_flatline_run=_longest_flatline(col),
                )
            )

        n_dupe_ts, n_gaps, largest_gap = self._timestamp_integrity(series.timestamps)

        return QualityResult(
            artifact_id=f"{series.manifest.unit}__quality",
            provenance=Provenance(
                engine=ENGINE_NAME,
                engine_version=ENGINE_VERSION,
                source_unit=series.manifest.unit,
                input_hash=_input_hash(frame),
            ),
            unit=series.manifest.unit,
            n_rows=n_rows,
            sensors=tuple(sensors),
            n_duplicate_timestamps=n_dupe_ts,
            n_gaps=n_gaps,
            largest_gap_hours=largest_gap,
            empty_columns=tuple(empty_columns),
        )

    def _timestamp_integrity(self, ts: pd.Series) -> tuple[int, int, float | None]:
        ts_sorted = ts.dropna().sort_values()
        n_dupe = int(ts_sorted.duplicated().sum())
        diffs = ts_sorted.diff().dropna()
        gap_mask = diffs > pd.Timedelta(hours=self._gap_hours)
        n_gaps = int(gap_mask.sum())
        largest = (
            round(diffs.max().total_seconds() / 3600.0, 2) if len(diffs) else None
        )
        return n_dupe, n_gaps, largest
