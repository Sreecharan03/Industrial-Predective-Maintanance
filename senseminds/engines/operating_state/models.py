"""Operating-state engine result models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.domain.results import EngineResult


class StateEpisode(FrozenModel):
    """One contiguous period the machine spent in a single operating state."""

    state: str = Field(description="Density-derived band label.")
    final_state: str = Field(description="Label after transition refinement.")
    start: datetime
    end: datetime
    dur_min: float = Field(ge=0.0, description="Dwell time (gap-capped) in minutes.")
    n_readings: int = Field(ge=0)


class StateSummary(FrozenModel):
    """Aggregate dwell across all episodes of one final state."""

    state: str
    total_minutes: float = Field(ge=0.0)
    total_hours: float = Field(ge=0.0)
    episodes: int = Field(ge=0)
    avg_episode_minutes: float = Field(ge=0.0)
    pct_of_covered_time: float = Field(ge=0.0, le=100.0)


class MachineOperatingStates(FrozenModel):
    """Operating-state segmentation for one machine (a unit may have several)."""

    machine_label: str
    indicator_key: str = Field(description="Sensor key the states were segmented from.")
    segmentable: bool = Field(description="False if too little indicator data to segment.")
    cutpoints: tuple[float, ...] = Field(default_factory=tuple)
    band_labels: dict[int, str] = Field(default_factory=dict)
    off_label: str | None = None
    total_covered_hours: float = Field(default=0.0, ge=0.0)
    summary: tuple[StateSummary, ...] = Field(default_factory=tuple)
    episodes: tuple[StateEpisode, ...] = Field(default_factory=tuple)
    note: str = Field(default="")

    def state(self, label: str) -> StateSummary | None:
        return next((s for s in self.summary if s.state == label), None)


class OperatingStateResult(EngineResult):
    """Operating-state segmentation for a unit (all its machines)."""

    unit: str
    machines: tuple[MachineOperatingStates, ...]

    def machine(self, label: str) -> MachineOperatingStates | None:
        return next((m for m in self.machines if m.machine_label == label), None)
