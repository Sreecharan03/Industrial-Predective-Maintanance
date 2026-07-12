"""Operational Timeline result models.

Immutable public contract. Turns the Operating State engine's episodes into a
meaningful operational timeline: fine-grained events, coarse running/idle
segments, per-state durations (reused from upstream), and runtime rollups.
Domain events, evidence, metadata, and provenance are kept separate.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.results import EngineResult
from senseminds.domain.value_objects import Confidence


class TimelineEvidence(FrozenModel):
    """Why an event began and ended - for future LLM reasoning."""

    reason_started: str
    reason_ended: str
    operating_state: str
    threshold_context: str
    confidence: Confidence


class TimelineEvent(FrozenModel):
    """One continuous operational event (a state episode, semantically typed)."""

    event_type: str = Field(description="e.g. machine_started, entered_full_load, machine_idle.")
    state: str
    start: datetime
    end: datetime
    duration_minutes: float = Field(ge=0.0)
    evidence: TimelineEvidence


class TimelineSegment(FrozenModel):
    """A coarse operational period: a merged run of running or idle events."""

    segment_type: str = Field(description="'running' or 'idle'.")
    start: datetime
    end: datetime
    duration_hours: float = Field(ge=0.0)
    n_events: int = Field(ge=0)


class StateDuration(FrozenModel):
    """How long the machine spent in one operating state (reused upstream)."""

    state: str
    total_hours: float = Field(ge=0.0)
    pct_of_covered_time: float = Field(ge=0.0, le=100.0)
    episodes: int = Field(ge=0)


class ContinuousPeriod(FrozenModel):
    """The longest / representative running or idle stretch."""

    duration_hours: float = Field(ge=0.0)
    start: datetime | None = None
    end: datetime | None = None


class RuntimeRollup(FrozenModel):
    """Aggregate runtime behaviour (Phase-2 Runtime report equivalents)."""

    days_with_data: int = Field(ge=0)
    avg_utilization_pct: float = Field(ge=0.0, le=100.0)
    daily_running_hours_p5: float | None = None
    daily_running_hours_p25: float | None = None
    daily_running_hours_median: float | None = None
    daily_running_hours_p75: float | None = None
    daily_running_hours_p95: float | None = None
    n_running_segments: int = Field(ge=0)
    n_idle_segments: int = Field(ge=0)
    longest_run: ContinuousPeriod | None = None
    median_run_hours: float | None = None
    longest_idle: ContinuousPeriod | None = None
    median_idle_hours: float | None = None


class TimelineMetadata(FrozenModel):
    """How the timeline was built and over what window."""

    window_start: datetime | None = None
    window_end: datetime | None = None
    total_covered_hours: float = Field(ge=0.0)
    gap_cap_minutes: int
    note: str = ""


class MachineTimeline(FrozenModel):
    """The operational timeline for one machine of a unit."""

    machine_label: str
    events: tuple[TimelineEvent, ...] = Field(default_factory=tuple)
    segments: tuple[TimelineSegment, ...] = Field(default_factory=tuple)
    state_durations: tuple[StateDuration, ...] = Field(default_factory=tuple)
    runtime: RuntimeRollup | None = None
    metadata: TimelineMetadata


class OperationalTimelineResult(EngineResult):
    """Operational timeline for a unit (all its machines), immutable."""

    unit: str
    machines: tuple[MachineTimeline, ...]

    def machine(self, label: str) -> MachineTimeline | None:
        return next((m for m in self.machines if m.machine_label == label), None)
