"""Internal runtime math for the Operational Timeline engine.

Faithful port of Phase-2 ``step9`` (expand-to-calendar, daily runtime table,
run-block merging). Kept private to the engine package - consumers see only
the typed timeline models, never this histogram/aggregation detail. Operates
on the episode list already produced by the Operating State engine; recomputes
no upstream information.
"""

from __future__ import annotations

import pandas as pd

GAP_CAP_MIN = 120  # 2 h - matches the state engine's dwell cap


def _is_off(final_state: pd.Series) -> pd.Series:
    return final_state.str.contains("OFF")


def expand_to_calendar(start: pd.Timestamp, end: pd.Timestamp, dur_min: float) -> list[tuple]:
    """Distribute an episode's minutes across the calendar day(s) it spans."""
    if pd.isna(start) or pd.isna(end) or dur_min <= 0:
        return []
    if start.normalize() == end.normalize():
        return [(start.date(), dur_min)]
    days = pd.date_range(start.normalize(), end.normalize(), freq="D")
    total_span = max((end - start).total_seconds(), 1e-9)
    out = []
    for d in days:
        day_start = max(start, d)
        day_end = min(end, d + pd.Timedelta(days=1))
        frac = max((day_end - day_start).total_seconds(), 0) / total_span
        if frac > 0:
            out.append((d.date(), dur_min * frac))
    return out


def daily_runtime_table(episodes: pd.DataFrame) -> pd.DataFrame:
    """Per-day covered/running hours and utilization (days with data only)."""
    is_off = _is_off(episodes["final_state"])
    rows = []
    for start, end, dur_min, off in zip(
        episodes["start"], episodes["end"], episodes["dur_min"], is_off, strict=True
    ):
        for date, minutes in expand_to_calendar(pd.Timestamp(start), pd.Timestamp(end), dur_min):
            rows.append({"date": date, "minutes": minutes, "is_off": off})
    d = pd.DataFrame(rows)
    if d.empty:
        return pd.DataFrame(columns=["date", "covered_hours", "running_hours", "utilization_pct"])
    covered = d.groupby("date")["minutes"].sum().rename("covered_minutes")
    running = d[~d["is_off"]].groupby("date")["minutes"].sum().rename("running_minutes")
    daily = pd.concat([covered, running], axis=1).fillna(0.0).reset_index()
    daily["covered_hours"] = daily["covered_minutes"] / 60.0
    daily["running_hours"] = daily["running_minutes"] / 60.0
    daily["utilization_pct"] = (100 * daily["running_hours"] / daily["covered_hours"]).round(2)
    return daily.sort_values("date")[["date", "covered_hours", "running_hours", "utilization_pct"]]


def merge_run_blocks(episodes: pd.DataFrame, cap_minutes: int = GAP_CAP_MIN) -> pd.DataFrame:
    """Merge consecutive episodes into running / idle blocks (split on gaps)."""
    d = episodes.sort_values("start").reset_index(drop=True).copy()
    d["start"] = pd.to_datetime(d["start"])
    d["end"] = pd.to_datetime(d["end"])
    d["is_off"] = _is_off(d["final_state"])
    gap_from_prev = (d["start"] - d["end"].shift()).dt.total_seconds() / 60.0
    new_block = (
        (d["is_off"] != d["is_off"].shift())
        | (gap_from_prev > cap_minutes)
        | gap_from_prev.isna()
    )
    block_id = new_block.cumsum()
    return (
        d.groupby(block_id)
        .agg(
            is_off=("is_off", "first"),
            start=("start", "first"),
            end=("end", "last"),
            dur_min=("dur_min", "sum"),
            n_events=("is_off", "size"),
        )
        .reset_index(drop=True)
    )


def percentile_hours(daily: pd.DataFrame) -> dict[str, float]:
    if daily.empty:
        return {k: float("nan") for k in ("p5", "p25", "median", "p75", "p95")}
    h = daily["running_hours"]
    return {
        "p5": float(h.quantile(0.05)),
        "p25": float(h.quantile(0.25)),
        "median": float(h.median()),
        "p75": float(h.quantile(0.75)),
        "p95": float(h.quantile(0.95)),
    }


def episodes_to_frame(records: list[dict]) -> pd.DataFrame:
    """Build the working frame from typed StateEpisode records."""
    if not records:
        return pd.DataFrame(columns=["start", "end", "dur_min", "final_state"])
    return pd.DataFrame.from_records(records)
