"""Wide frame → readings (ADR-019 D2).

Turns an `IngestedSeries` (timestamp + sensor-key columns) into the atomic
`Reading` stream a sink persists. Emits a reading for **every** (timestamp,
sensor) cell - including NaN - so the observation grid is preserved end to end
(NaN becomes a MISSING reading at validation). Pure transform.
"""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd

from senseminds.ingestion.models import TIMESTAMP_COLUMN, IngestedSeries
from senseminds.ingestion.reading import Reading


def iter_readings(series: IngestedSeries, source: str = "csv_bootstrap") -> Iterator[Reading]:
    """Yield one Reading per (timestamp, sensor) cell of the series frame."""
    unit = series.manifest.unit
    keys = series.manifest.sensor_keys
    frame = series.frame
    times = [ts.to_pydatetime() for ts in frame[TIMESTAMP_COLUMN]]
    columns = {key: frame[key].to_numpy() for key in keys}
    for i, time in enumerate(times):
        for key in keys:
            raw = columns[key][i]
            value = None if pd.isna(raw) else float(raw)
            yield Reading(unit=unit, sensor_key=key, time=time, value=value, source=source)
