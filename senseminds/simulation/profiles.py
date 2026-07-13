"""Learn a per-sensor statistical profile from a machine's real history.

Synthetic live data is only useful if it behaves like the machine it imitates, so
each sensor's level, spread, daily cycle and plausible range are measured from the
real processed data rather than invented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from senseminds.ingestion import ProcessedCsvSource


@dataclass(frozen=True)
class SensorProfile:
    source_column: str
    base: float      # typical level (median)
    sd: float        # tick-to-tick noise
    lo: float        # plausible floor (p01)
    hi: float        # plausible ceiling (p99)
    amp: float       # daily-cycle amplitude
    peak_hour: float  # hour of day the cycle peaks


def _daily_cycle(times: pd.Series, values: pd.Series) -> tuple[float, float]:
    """Amplitude + peak hour of the 24h cycle, by hourly means."""
    hours = times.dt.hour + times.dt.minute / 60.0
    frame = pd.DataFrame({"h": hours.astype(int), "v": values}).dropna()
    if frame.empty:
        return 0.0, 0.0
    means = frame.groupby("h")["v"].mean()
    if len(means) < 6 or not np.isfinite(means).all():
        return 0.0, 0.0
    amp = float((means.max() - means.min()) / 2.0)
    return (0.0, 0.0) if not math.isfinite(amp) else (amp, float(means.idxmax()))


def profile_unit(processed_dir: Path, unit: str) -> tuple[list[SensorProfile], list[str]]:
    """Return (profiles, source_columns-in-order) for one machine."""
    series = ProcessedCsvSource(processed_dir).load(unit)
    frame, times = series.frame, series.frame["timestamp"]

    profiles: list[SensorProfile] = []
    columns: list[str] = []
    for sensor in series.asset.sensors:
        values = frame[sensor.key].dropna()
        if values.empty:
            continue
        amp, peak = _daily_cycle(times[frame[sensor.key].notna()], values)
        sd = float(values.diff().abs().median() or 0.0) or float(values.std() * 0.05)
        profiles.append(
            SensorProfile(
                source_column=sensor.source_column,
                base=float(values.median()),
                sd=max(sd, 1e-6),
                lo=float(values.quantile(0.01)),
                hi=float(values.quantile(0.99)),
                amp=amp,
                peak_hour=peak,
            )
        )
        columns.append(sensor.source_column)
    return profiles, columns
