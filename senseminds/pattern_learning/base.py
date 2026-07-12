"""Pattern-model interface + shared helpers (ADR-016 §8)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime

import numpy as np

from senseminds.pattern_learning.models import FeatureFrame, ModelHealth, PatternLifecycle


class PatternModel(ABC):
    """A label-free pattern model: fit + score a FeatureFrame into a result."""

    name: str
    version: str

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    @abstractmethod
    def run(self, features: FeatureFrame):  # noqa: ANN201 - returns PatternResult
        """Fit on the features and emit LEARNED hypotheses (never facts)."""


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def model_health(features: FeatureFrame) -> ModelHealth:
    """Assess the trustworthiness of a model run over these features (ADR-016 R1)."""
    if features.n_windows == 0:
        return ModelHealth(
            coverage_pct=0.0, feature_completeness_pct=0.0, drift_indicator=0.0,
            reproducible=True, note="no windows",
        )
    completeness = 100.0 * float((features.matrix != 0).any(axis=0).mean())
    drift = _drift(features.matrix)
    return ModelHealth(
        coverage_pct=features.coverage_pct,
        feature_completeness_pct=round(completeness, 2),
        drift_indicator=round(drift, 4),
        reproducible=True,
        note="seeded model over engineered features",
    )


def _drift(matrix: np.ndarray) -> float:
    """Mean per-feature shift between the first and second half of the windows."""
    n = matrix.shape[0]
    if n < 4:
        return 0.0
    half = n // 2
    return float(np.abs(matrix[:half].mean(axis=0) - matrix[half:].mean(axis=0)).mean())


def matrix_hash(matrix: np.ndarray) -> str:
    """Deterministic content hash of a feature matrix (for finding provenance)."""
    return hashlib.sha256(np.ascontiguousarray(matrix).tobytes()).hexdigest()[:16]


def lifecycle_from_indices(indices: list[int], n_windows: int) -> PatternLifecycle:
    """Lifecycle metadata from where a pattern's windows fall in time (ADR-016 R3)."""
    if not indices or n_windows == 0:
        return PatternLifecycle.INACTIVE
    recency = max(indices) / max(n_windows - 1, 1)
    fraction = len(indices) / n_windows
    if recency < 0.5:
        return PatternLifecycle.DECLINING
    if fraction >= 0.3:
        return PatternLifecycle.STABLE
    return PatternLifecycle.EMERGING
