"""Isolation-Forest novelty model (ADR-016 §3).

Unsupervised 'this window is unlike history' scoring over engineered features.
Emits a single LEARNED NOVELTY_ELEVATED finding when novelty exceeds a threshold,
with the principal contributing features (explainable learning, R4). Framed as
'unlike history', never 'fault'; advisory only. Reproducible: fixed seed +
feature snapshot -> identical scores.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
    ObservedWindow,
)
from senseminds.findings.identity import finding_id, identity_key
from senseminds.pattern_learning.base import (
    PatternModel,
    lifecycle_from_indices,
    matrix_hash,
    model_health,
    now_utc,
)
from senseminds.pattern_learning.models import (
    DiscoveredPattern,
    FeatureFrame,
    PatternResult,
)

_MIN_WINDOWS = 5


class IsolationForestNovelty(PatternModel):
    """Novelty scoring via Isolation Forest."""

    name = "isolation_forest_novelty"
    version = "0.1.0"

    def __init__(self, seed: int = 0, threshold: float = 0.6, n_estimators: int = 100) -> None:
        super().__init__(seed)
        self._threshold = threshold
        self._n_estimators = n_estimators

    def run(self, features: FeatureFrame) -> PatternResult:
        health = model_health(features)
        if features.n_windows < _MIN_WINDOWS:
            return PatternResult(
                unit=features.unit, model_id=self.name, model_version=self.version,
                model_health=health, extras={"note": "insufficient windows to score novelty"},
            )

        clf = IsolationForest(
            n_estimators=self._n_estimators, random_state=self.seed, contamination="auto"
        )
        clf.fit(features.matrix)
        raw = -clf.score_samples(features.matrix)  # higher = more anomalous
        lo, hi = float(raw.min()), float(raw.max())
        novelty = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)

        novel_idx = [int(i) for i in np.where(novelty >= self._threshold)[0]]
        if not novel_idx:
            return PatternResult(
                unit=features.unit, model_id=self.name, model_version=self.version,
                model_health=health, extras={"max_novelty": round(float(novelty.max()), 4)},
            )

        peak = int(np.argmax(novelty))
        max_novelty = round(float(novelty[peak]), 4)
        contrib = self._contributing(features, peak)
        input_hash = matrix_hash(features.matrix)
        idk = identity_key(
            features.unit, FindingType.NOVELTY_ELEVATED, FindingScope.EQUIPMENT, features.unit
        )

        evidence = (
            Evidence(
                artifact_id=f"model:{self.name}@{self.version}",
                description="novelty score (unlike historical behaviour)",
                observed_value=max_novelty,
            ),
            *(
                Evidence(
                    artifact_id=f"model:{self.name}@{self.version}",
                    description=f"contributing feature {name}",
                    observed_value=round(dev, 4),
                )
                for name, dev in contrib
            ),
        )
        conf = round(max_novelty * health.coverage_pct / 100, 4)
        finding = Finding(
            finding_id=finding_id(idk, input_hash), identity_key=idk,
            finding_type=FindingType.NOVELTY_ELEVATED, category=FindingCategory.ANOMALY,
            scope=FindingScope.EQUIPMENT, origin=FindingOrigin.LEARNED,
            summary=f"Behaviour unlike history in {len(novel_idx)} window(s) (hypothesis)",
            detail="Principal drivers: "
            + ", ".join(f"{n} ({d:+.2f})" for n, d in contrib),
            target_key=features.unit, equipment_key=features.unit,
            severity=Severity.INFO,
            confidence=Confidence(value=max(0.0, min(1.0, conf)), rationale="novelty x coverage"),
            evidence=evidence, source_engine=f"model:{self.name}@{self.version}",
            observed_window=ObservedWindow(
                start=features.window_starts[0], end=features.window_ends[-1]
            ),
            provenance=Provenance(
                engine="pattern_learning", engine_version=self.version,
                source_unit=features.unit, input_hash=input_hash, produced_at=now_utc(),
            ),
        )
        pattern = DiscoveredPattern(
            pattern_id=f"novelty:{features.unit}:{input_hash}", model_id=self.name,
            model_version=self.version, kind="novelty",
            label=f"novelty in {len(novel_idx)} windows", support_windows=len(novel_idx),
            confidence=finding.confidence.value,
            lifecycle=lifecycle_from_indices(novel_idx, features.n_windows),
            descriptor={"max_novelty": max_novelty, "drivers": [n for n, _ in contrib]},
        )
        return PatternResult(
            unit=features.unit, model_id=self.name, model_version=self.version,
            findings=(finding,), patterns=(pattern,), model_health=health,
        )

    @staticmethod
    def _contributing(features: FeatureFrame, window: int, top: int = 3) -> list[tuple[str, float]]:
        row = features.matrix[window]
        order = np.argsort(-np.abs(row))[:top]
        return [(features.feature_names[i], float(row[i])) for i in order]
