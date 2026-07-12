"""Episode building - collapse per-row states into contiguous episodes.

Faithful port of the Phase-2 ``build_episodes`` / ``refine_transitions``.
Dwell time is the sum of inter-reading gaps capped at ``GAP_CAP_MIN``; a gap
longer than the cap both caps that interval's contribution and forces a new
episode (state continuity across an unlogged multi-hour/day gap is not
assumed). Short episodes bridging OFF and a loaded band are relabeled as
startup/shutdown transitions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from senseminds.engines.operating_state.segmentation import GAP_CAP_MIN, SHORT_EPISODE_MIN

STATE_COLUMN = "__state__"
TIMESTAMP_COLUMN = "timestamp"


def build_episodes(
    frame: pd.DataFrame, state_col: str, cap_minutes: int = GAP_CAP_MIN
) -> pd.DataFrame:
    """Collapse a per-row state series into contiguous episodes with dwell time."""
    d = (
        frame[[TIMESTAMP_COLUMN, state_col]]
        .dropna(subset=[state_col])
        .sort_values(TIMESTAMP_COLUMN)
        .reset_index(drop=True)
    )
    if d.empty:
        return pd.DataFrame(columns=["state", "start", "end", "dur_min", "n_readings"])
    gap_from_prev = d[TIMESTAMP_COLUMN].diff().dt.total_seconds() / 60.0
    new_segment = (
        (d[state_col] != d[state_col].shift())
        | (gap_from_prev > cap_minutes)
        | gap_from_prev.isna()
    )
    seg_id = new_segment.cumsum()
    minutes_to_next = (
        d[TIMESTAMP_COLUMN].shift(-1) - d[TIMESTAMP_COLUMN]
    ).dt.total_seconds() / 60.0
    d["dur_min"] = np.where(
        (minutes_to_next.notna()) & (minutes_to_next <= cap_minutes), minutes_to_next, 0.0
    )
    return (
        d.groupby(seg_id)
        .agg(
            state=(state_col, "first"),
            start=(TIMESTAMP_COLUMN, "first"),
            end=(TIMESTAMP_COLUMN, "last"),
            dur_min=("dur_min", "sum"),
            n_readings=(TIMESTAMP_COLUMN, "size"),
        )
        .reset_index(drop=True)
    )


def refine_transitions(
    episodes: pd.DataFrame, off_label: str, short_minutes: int = SHORT_EPISODE_MIN
) -> pd.DataFrame:
    """Relabel short episodes bridging OFF and a loaded band as startup/shutdown/
    load transitions; longer episodes keep their density-derived band label."""
    ep = episodes.copy()
    ep["final_state"] = ep["state"]
    for i in range(len(ep)):
        if ep.loc[i, "dur_min"] > short_minutes:
            continue
        prev_state = ep.loc[i - 1, "state"] if i > 0 else None
        next_state = ep.loc[i + 1, "state"] if i < len(ep) - 1 else None
        cur_state = ep.loc[i, "state"]
        if cur_state == off_label:
            continue
        if prev_state == off_label and next_state is not None and next_state != off_label:
            ep.loc[i, "final_state"] = "Startup / Pull-down"
        elif next_state == off_label and prev_state is not None and prev_state != off_label:
            ep.loc[i, "final_state"] = "Unloading / Shutdown"
        elif (
            prev_state is not None
            and next_state is not None
            and prev_state != cur_state
            and next_state != cur_state
            and prev_state != off_label
            and next_state != off_label
        ):
            ep.loc[i, "final_state"] = "Load Transition"
    return ep
