"""Operating-state engine.

Refactor of Phase-2 ``step6`` into a typed, stateless service. Infers each
machine's operating states from the historical distribution of its activity
indicator (Loading %, Receiver Pressure, or Nitrogen Flow Rate - see
ACTIVITY_INDICATORS), using density-valley segmentation + dwell-time/episode
analysis. Deterministic; no state count or boundary is hardcoded and no model
is fitted. Output matches Phase-2 exactly (tests/test_parity_operating_state.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from senseminds.engines.base import BaseEngine
from senseminds.engines.operating_state.episodes import (
    STATE_COLUMN,
    build_episodes,
    refine_transitions,
)
from senseminds.engines.operating_state.models import (
    MachineOperatingStates,
    OperatingStateResult,
    StateEpisode,
    StateSummary,
)
from senseminds.engines.operating_state.segmentation import (
    assign_band_labels,
    band_activity,
    describe_bands,
)
from senseminds.ingestion.models import IngestedSeries

# (sensor_key, machine_label) per unit - the best available "is it producing"
# indicator. Refrigeration units use Loading %, utility units their output
# proxy. Mirrors Phase-2 ACTIVITY_INDICATORS mapped to catalog sensor keys.
_TWIN = [
    ("loading_percentage_com1", "Compressor 1"),
    ("loading_percentage_com2", "Compressor 2"),
]
ACTIVITY_INDICATORS: dict[str, list[tuple[str, str]]] = {
    "SC-126": [("loading_percentage", "Compressor")],
    "SC-114": _TWIN,
    "SC-104": _TWIN,
    "COM-102": [("receiver_pressure", "Air Compressor")],
    "COM-110": [("receiver_pressure", "Air Compressor")],
    "COM103 & NP102": [("nitrogen_flow_rate", "PSA Nitrogen Plant")],
}

_MIN_POINTS = 30


def _continuous_labels(frame: pd.DataFrame, col: str) -> tuple[pd.Series, dict[int, str]]:
    """Single-band labeling when the indicator is unimodal (no distinct states)."""
    valid = frame[col].notna()
    band_idx = pd.Series(np.where(valid, 0, np.nan), index=frame.index)
    s = frame.loc[valid, col]
    mean_v = s.mean()
    cv = (s.std() / mean_v) if mean_v not in (0, np.nan) and mean_v != 0 else np.nan
    label = (
        "Continuous Stable Operation (no distinct load states detected)"
        if (pd.notna(cv) and abs(cv) < 0.15)
        else "Continuous Operation, Variable (no distinct load states detected)"
    )
    return band_idx, {0: label}


def _summarize(episodes: pd.DataFrame) -> tuple[list[StateSummary], float]:
    total_covered = float(episodes["dur_min"].sum())
    grouped = (
        episodes.groupby("final_state")
        .agg(
            total_min=("dur_min", "sum"),
            episodes=("dur_min", "size"),
            avg_min=("dur_min", "mean"),
        )
        .reset_index()
        .sort_values("total_min", ascending=False)
    )
    summaries = [
        StateSummary(
            state=row["final_state"],
            total_minutes=float(row["total_min"]),
            total_hours=float(row["total_min"]) / 60.0,
            episodes=int(row["episodes"]),
            avg_episode_minutes=float(row["avg_min"]),
            pct_of_covered_time=round(100 * float(row["total_min"]) / total_covered, 2)
            if total_covered
            else 0.0,
        )
        for _, row in grouped.iterrows()
    ]
    return summaries, total_covered


def _episode_models(episodes: pd.DataFrame) -> tuple[StateEpisode, ...]:
    return tuple(
        StateEpisode(
            state=row["state"],
            final_state=row["final_state"],
            start=pd.Timestamp(row["start"]).to_pydatetime(),
            end=pd.Timestamp(row["end"]).to_pydatetime(),
            dur_min=float(row["dur_min"]),
            n_readings=int(row["n_readings"]),
        )
        for _, row in episodes.iterrows()
    )


def _analyze_machine(
    frame: pd.DataFrame, indicator_key: str, machine_label: str
) -> MachineOperatingStates:
    if indicator_key not in frame.columns or frame[indicator_key].dropna().shape[0] < _MIN_POINTS:
        return MachineOperatingStates(
            machine_label=machine_label,
            indicator_key=indicator_key,
            segmentable=False,
            note="Insufficient valid indicator data to segment operating states.",
        )

    cutpoints = band_activity(frame[indicator_key])
    if not cutpoints:
        band_idx, band_labels = _continuous_labels(frame, indicator_key)
    else:
        band_idx = assign_band_labels(frame, indicator_key, cutpoints)
        band_labels = describe_bands(frame, indicator_key, band_idx)

    work = frame.copy()
    work[STATE_COLUMN] = band_idx.map(band_labels)
    episodes = build_episodes(work, STATE_COLUMN)
    off_label = next((v for v in band_labels.values() if "OFF" in v), None)
    episodes = (
        refine_transitions(episodes, off_label)
        if off_label
        else episodes.assign(final_state=episodes["state"])
    )

    summaries, total_covered = _summarize(episodes)
    return MachineOperatingStates(
        machine_label=machine_label,
        indicator_key=indicator_key,
        segmentable=True,
        cutpoints=tuple(cutpoints),
        band_labels=band_labels,
        off_label=off_label,
        total_covered_hours=total_covered / 60.0,
        summary=tuple(summaries),
        episodes=_episode_models(episodes),
    )


class OperatingStateEngine(BaseEngine):
    """Segment a unit's machines into operating states from historical behaviour."""

    name = "operating_state"
    version = "0.1.0"

    def compute(self, series: IngestedSeries) -> OperatingStateResult:
        unit = series.manifest.unit
        indicators = ACTIVITY_INDICATORS.get(unit, [])
        machines = tuple(
            _analyze_machine(series.frame, key, label) for key, label in indicators
        )
        self.log.info("operating_states_computed", extra={"unit": unit, "machines": len(machines)})
        return OperatingStateResult(
            artifact_id=f"{unit}__operating_state",
            provenance=self.provenance_from_frame(unit, series.frame),
            unit=unit,
            machines=machines,
        )
