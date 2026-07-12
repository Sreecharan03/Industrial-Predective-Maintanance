"""Health engine result models.

Immutable container over the domain `HealthScore` tree for one unit:
equipment health at the top, its subsystems, and the individual sensors. Each
`HealthScore` carries its own severity, confidence (from sensor reliability),
contributing factors, and evidence ids - so the tree is interrogable top-down
and every score is traceable (ADR-008).
"""

from __future__ import annotations

from senseminds.domain.entities import HealthScore
from senseminds.domain.results import EngineResult


class HealthResult(EngineResult):
    """Hierarchical health for a unit: equipment -> subsystems -> sensors."""

    unit: str
    equipment: HealthScore
    subsystems: tuple[HealthScore, ...]
    sensors: tuple[HealthScore, ...]

    def subsystem(self, key: str) -> HealthScore | None:
        return next((s for s in self.subsystems if s.target_key == key), None)

    def sensor(self, key: str) -> HealthScore | None:
        return next((s for s in self.sensors if s.target_key == key), None)
