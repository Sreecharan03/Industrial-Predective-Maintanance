"""Synthesise 30-second machine data from a learned profile.

Every value = level + daily cycle + noise, bounded by the sensor's plausible range.
An optional **drift** ramps one sensor toward (and past) an operating limit once the
live phase starts, so the platform visibly reacts: the threshold engine's current
state flips, severity rises, and a new finding appears on the dashboard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from senseminds.simulation.profiles import SensorProfile

TICK = timedelta(seconds=30)


@dataclass(frozen=True)
class Drift:
    """Ramp one sensor from its normal level to `target` over `ramp_minutes`."""

    unit: str
    source_column: str
    target: float
    ramp_minutes: float = 20.0


class MachineGenerator:
    """Generates one machine's rows at a 30-second cadence."""

    def __init__(
        self,
        unit: str,
        profiles: list[SensorProfile],
        live_start: datetime,
        drift: Drift | None = None,
        seed: int = 7,
    ) -> None:
        self.unit = unit
        self._profiles = profiles
        self._live_start = live_start
        self._drift = drift
        self._rng = np.random.default_rng(seed)

    def _drift_offset(self, p: SensorProfile, t: datetime) -> float:
        d = self._drift
        if d is None or d.source_column != p.source_column or t < self._live_start:
            return 0.0
        elapsed = (t - self._live_start).total_seconds() / 60.0
        progress = min(1.0, elapsed / max(d.ramp_minutes, 1e-6))
        return (d.target - p.base) * progress

    def row(self, t: datetime) -> dict[str, object]:
        out: dict[str, object] = {"timestamp": t.isoformat(sep=" ")}
        hour = t.hour + t.minute / 60.0
        for p in self._profiles:
            cycle = p.amp * math.sin(2 * math.pi * (hour - p.peak_hour) / 24.0 + math.pi / 2)
            noise = float(self._rng.normal(0.0, p.sd))
            value = p.base + cycle + noise
            value = min(max(value, p.lo), p.hi)      # healthy values stay plausible
            value += self._drift_offset(p, t)        # drift may legitimately exceed
            out[p.source_column] = round(value, 2)
        return out

    def rows_between(self, start: datetime, end: datetime) -> list[dict[str, object]]:
        rows, t = [], start
        while t <= end:
            rows.append(self.row(t))
            t += TICK
        return rows


def align_to_tick(t: datetime) -> datetime:
    """Snap down to the previous :00 / :30 second boundary."""
    return t.replace(second=0 if t.second < 30 else 30, microsecond=0)
