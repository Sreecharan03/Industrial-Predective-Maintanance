"""Operational Timeline engine.

Transforms the Operating State engine's episodes into a meaningful operational
timeline: semantically-typed events, coarse running/idle segments, and runtime
rollups. Consumes ONLY engine contracts (OperatingStateResult + optional
ThresholdResult) - never raw series - and recomputes no upstream information.
Runtime rollups reproduce Phase-2 exactly (tests/test_parity_operational_timeline.py).
"""

from __future__ import annotations

import pandas as pd

from senseminds.domain.value_objects import Confidence
from senseminds.engines.base import BaseEngine
from senseminds.engines.exceptions import EngineInputError
from senseminds.engines.operating_state.models import MachineOperatingStates, OperatingStateResult
from senseminds.engines.operational_timeline import runtime_math as rt
from senseminds.engines.operational_timeline.models import (
    ContinuousPeriod,
    MachineTimeline,
    OperationalTimelineResult,
    RuntimeRollup,
    StateDuration,
    TimelineEvent,
    TimelineEvidence,
    TimelineMetadata,
    TimelineSegment,
)
from senseminds.engines.threshold.models import ThresholdResult


def _event_type(final_state: str) -> str:
    s = final_state.lower()
    if "off" in s or "idle" in s:
        return "machine_idle"
    if "startup" in s or "pull-down" in s:
        return "machine_started"
    if "unloading" in s or "shutdown" in s:
        return "machine_stopped"
    if "full load" in s:
        return "entered_full_load"
    if "high load" in s:
        return "entered_high_load"
    if "partial" in s:
        return "entered_partial_load"
    if "transition" in s:
        return "load_transition"
    if "continuous" in s:
        return "continuous_operation"
    return "state_change"


def _nan_to_none(value: float) -> float | None:
    return None if pd.isna(value) else float(value)


class OperationalTimelineEngine(BaseEngine):
    """Build a unit's operational timeline from upstream engine results.

    ``min_event_minutes`` optionally omits sub-threshold events from the fine
    event list to reduce noise; segments and rollups are unaffected (durations
    stay exact). Default 0 keeps every (already-debounced) episode as an event.
    """

    name = "operational_timeline"
    version = "0.1.0"

    def __init__(self, min_event_minutes: float = 0.0) -> None:
        if min_event_minutes < 0:
            raise ValueError("min_event_minutes must be >= 0")
        self._min_event = min_event_minutes

    def compute(
        self, states: OperatingStateResult, thresholds: ThresholdResult | None = None
    ) -> OperationalTimelineResult:
        unit = states.unit
        if thresholds is not None and thresholds.unit != unit:
            raise EngineInputError(
                f"threshold unit {thresholds.unit!r} does not match state unit {unit!r}"
            )
        threshold_ctx = self._threshold_context(thresholds)
        machines = tuple(self._machine_timeline(m, threshold_ctx) for m in states.machines)
        self.log.info("timeline_built", extra={"unit": unit, "machines": len(machines)})
        return OperationalTimelineResult(
            artifact_id=f"{unit}__operational_timeline",
            # derived from the same source data as the state result
            provenance=self.provenance(unit, input_hash=states.provenance.input_hash),
            unit=unit,
            machines=machines,
        )

    @staticmethod
    def _threshold_context(thresholds: ThresholdResult | None) -> str:
        if thresholds is None:
            return "No threshold context supplied."
        breaches = [
            (s.sensor_key, s.history.pct_outside)
            for s in thresholds.sensors
            if s.history is not None
        ]
        if not breaches:
            return "No thresholded sensors for this unit."
        key, pct = max(breaches, key=lambda kv: kv[1])
        return f"Most notable: {key} outside operating range {pct}% of history (Threshold Engine)."

    def _machine_timeline(
        self, machine: MachineOperatingStates, threshold_ctx: str
    ) -> MachineTimeline:
        episodes = machine.episodes
        state_durations = tuple(
            StateDuration(
                state=s.state,
                total_hours=s.total_hours,
                pct_of_covered_time=s.pct_of_covered_time,
                episodes=s.episodes,
            )
            for s in machine.summary
        )
        if not machine.segmentable or not episodes:
            return MachineTimeline(
                machine_label=machine.machine_label,
                state_durations=state_durations,
                metadata=TimelineMetadata(
                    total_covered_hours=machine.total_covered_hours,
                    gap_cap_minutes=rt.GAP_CAP_MIN,
                    note="Not segmentable - insufficient indicator data.",
                ),
            )

        events = self._build_events(episodes, threshold_ctx)
        frame = rt.episodes_to_frame(
            [
                {"start": e.start, "end": e.end, "dur_min": e.dur_min, "final_state": e.final_state}
                for e in episodes
            ]
        )
        blocks = rt.merge_run_blocks(frame)
        segments = self._build_segments(blocks)
        runtime = self._build_rollup(frame, blocks)
        metadata = TimelineMetadata(
            window_start=pd.Timestamp(frame["start"].min()).to_pydatetime(),
            window_end=pd.Timestamp(frame["end"].max()).to_pydatetime(),
            total_covered_hours=machine.total_covered_hours,
            gap_cap_minutes=rt.GAP_CAP_MIN,
        )
        return MachineTimeline(
            machine_label=machine.machine_label,
            events=events,
            segments=segments,
            state_durations=state_durations,
            runtime=runtime,
            metadata=metadata,
        )

    def _build_events(self, episodes: tuple, threshold_ctx: str) -> tuple[TimelineEvent, ...]:
        events: list[TimelineEvent] = []
        n = len(episodes)
        for i, e in enumerate(episodes):
            if e.dur_min < self._min_event:
                continue
            prev_state = episodes[i - 1].final_state if i > 0 else None
            next_state = episodes[i + 1].final_state if i < n - 1 else None
            conf = 1 - 1 / (1 + e.n_readings)
            events.append(
                TimelineEvent(
                    event_type=_event_type(e.final_state),
                    state=e.final_state,
                    start=e.start,
                    end=e.end,
                    duration_minutes=e.dur_min,
                    evidence=TimelineEvidence(
                        reason_started=f"{prev_state or 'history start'} -> {e.final_state}",
                        reason_ended=f"{e.final_state} -> {next_state or 'history end'}",
                        operating_state=e.final_state,
                        threshold_context=threshold_ctx,
                        confidence=Confidence(
                            value=conf,
                            rationale=f"{e.n_readings} reading(s) support this event.",
                        ),
                    ),
                )
            )
        return tuple(events)

    @staticmethod
    def _build_segments(blocks: pd.DataFrame) -> tuple[TimelineSegment, ...]:
        return tuple(
            TimelineSegment(
                segment_type="idle" if row["is_off"] else "running",
                start=pd.Timestamp(row["start"]).to_pydatetime(),
                end=pd.Timestamp(row["end"]).to_pydatetime(),
                duration_hours=row["dur_min"] / 60.0,
                n_events=int(row["n_events"]),
            )
            for _, row in blocks.iterrows()
        )

    @staticmethod
    def _build_rollup(frame: pd.DataFrame, blocks: pd.DataFrame) -> RuntimeRollup:
        daily = rt.daily_runtime_table(frame)
        pct = rt.percentile_hours(daily)

        running = blocks[~blocks["is_off"]].copy()
        idle = blocks[blocks["is_off"] & (blocks["dur_min"] > 0)].copy()

        def _longest(block_df: pd.DataFrame) -> tuple[ContinuousPeriod | None, float | None]:
            if block_df.empty:
                return None, None
            hours = block_df["dur_min"] / 60.0
            top = block_df.loc[hours.idxmax()]
            period = ContinuousPeriod(
                duration_hours=float(top["dur_min"]) / 60.0,
                start=pd.Timestamp(top["start"]).to_pydatetime(),
                end=pd.Timestamp(top["end"]).to_pydatetime(),
            )
            return period, round(float(hours.median()), 4)

        longest_run, median_run = _longest(running)
        longest_idle, median_idle = _longest(idle)

        avg_util = round(float(daily["utilization_pct"].mean()), 2) if len(daily) else 0.0
        return RuntimeRollup(
            days_with_data=len(daily),
            avg_utilization_pct=avg_util,
            daily_running_hours_p5=_nan_to_none(pct["p5"]),
            daily_running_hours_p25=_nan_to_none(pct["p25"]),
            daily_running_hours_median=_nan_to_none(pct["median"]),
            daily_running_hours_p75=_nan_to_none(pct["p75"]),
            daily_running_hours_p95=_nan_to_none(pct["p95"]),
            n_running_segments=len(running),
            n_idle_segments=len(idle),
            longest_run=longest_run,
            median_run_hours=median_run,
            longest_idle=longest_idle,
            median_idle_hours=median_idle,
        )
