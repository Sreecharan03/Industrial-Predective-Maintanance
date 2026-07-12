"""Pattern Learning (Phase B) models.

All learned outputs are hypotheses, never facts (ADR-016). `ModelHealth` is the
"reliability of the model itself"; `DiscoveredPattern` carries a lifecycle as
metadata; LEARNED findings expose their principal contributing features. The
feature frame is a plain dataclass because it carries a numpy matrix across the
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np
from pydantic import Field

from senseminds.domain.base import FrozenModel
from senseminds.findings import Finding

FEATURE_SCHEMA_VERSION = "1.0"


class PatternLifecycle(StrEnum):
    """Lifecycle of a discovered pattern - metadata on a hypothesis (ADR-016 R3)."""

    EMERGING = "emerging"
    STABLE = "stable"
    DECLINING = "declining"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class FeatureFrame:
    """Engineered per-window features (deterministic; from validated data)."""

    unit: str
    matrix: np.ndarray  # n_windows x n_features (z-normalised)
    feature_names: tuple[str, ...]
    window_starts: tuple[datetime, ...]
    window_ends: tuple[datetime, ...]
    n_readings: tuple[int, ...]
    coverage_pct: float
    feature_schema_version: str = FEATURE_SCHEMA_VERSION

    @property
    def n_windows(self) -> int:
        return self.matrix.shape[0]


class ModelHealth(FrozenModel):
    """Trustworthiness of a model run - the 'reliability' of the model (ADR-016 R1)."""

    coverage_pct: float = Field(ge=0.0, le=100.0)
    feature_completeness_pct: float = Field(ge=0.0, le=100.0)
    drift_indicator: float = Field(ge=0.0, description="Early-vs-recent feature shift.")
    reproducible: bool = Field(description="Seeded and deterministic given data + version.")
    note: str = ""


class ContributingFeature(FrozenModel):
    """A feature that drove a novelty score (ADR-016 R4 - explainable learning)."""

    feature: str
    deviation: float = Field(description="Signed z-score deviation in the driving window.")


class DiscoveredPattern(FrozenModel):
    """A learned regime/novelty pattern - a hypothesis with lifecycle metadata."""

    pattern_id: str
    model_id: str
    model_version: str
    kind: str = Field(description="'regime' or 'novelty'.")
    label: str
    support_windows: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    lifecycle: PatternLifecycle
    descriptor: dict[str, object] = Field(default_factory=dict)
    status: str = Field(default="hypothesis")


@dataclass(frozen=True)
class PatternResult:
    """Everything a model run produced: LEARNED findings + patterns + health."""

    unit: str
    model_id: str
    model_version: str
    findings: tuple[Finding, ...] = ()
    patterns: tuple[DiscoveredPattern, ...] = ()
    model_health: ModelHealth | None = None
    extras: dict[str, object] = field(default_factory=dict)
