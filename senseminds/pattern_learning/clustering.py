"""Operating-regime clustering (ADR-016 §3).

Unsupervised multivariate regime discovery via a Gaussian Mixture - an
*enrichment* of the deterministic 1-D operating states, not a replacement. Emits
a LEARNED OPERATING_REGIME_DISCOVERED finding + one DiscoveredPattern per regime,
each with lifecycle metadata. Reproducible via fixed seed.
"""

from __future__ import annotations

import numpy as np
from sklearn.mixture import GaussianMixture

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

_MIN_WINDOWS = 6


class RegimeClusterer(PatternModel):
    """Multivariate operating-regime discovery."""

    name = "gmm_regime_clusterer"
    version = "0.1.0"

    def __init__(self, seed: int = 0, n_regimes: int = 3) -> None:
        super().__init__(seed)
        self._n_regimes = n_regimes

    def run(self, features: FeatureFrame) -> PatternResult:
        health = model_health(features)
        k = min(self._n_regimes, features.n_windows)
        if features.n_windows < _MIN_WINDOWS or k < 2:
            return PatternResult(
                unit=features.unit, model_id=self.name, model_version=self.version,
                model_health=health, extras={"note": "insufficient windows to cluster"},
            )

        gmm = GaussianMixture(n_components=k, covariance_type="full", random_state=self.seed)
        labels = gmm.fit_predict(features.matrix)
        input_hash = matrix_hash(features.matrix)

        patterns = []
        for c in range(k):
            idx = [int(i) for i in np.where(labels == c)[0]]
            if not idx:
                continue
            centroid = gmm.means_[c]
            dom = np.argsort(-np.abs(centroid))[:3]
            drivers = [features.feature_names[i] for i in dom]
            patterns.append(
                DiscoveredPattern(
                    pattern_id=f"regime:{features.unit}:{input_hash}:{c}", model_id=self.name,
                    model_version=self.version, kind="regime",
                    label=f"regime {c} ({', '.join(drivers)})", support_windows=len(idx),
                    confidence=round(len(idx) / features.n_windows, 4),
                    lifecycle=lifecycle_from_indices(idx, features.n_windows),
                    descriptor={
                        "dominant_features": drivers,
                        "share_pct": round(100 * len(idx) / features.n_windows, 2),
                    },
                )
            )

        idk = identity_key(
            features.unit,
            FindingType.OPERATING_REGIME_DISCOVERED,
            FindingScope.EQUIPMENT,
            features.unit,
        )
        model_ref = f"model:{self.name}@{self.version}"
        evidence = tuple(
            Evidence(artifact_id=model_ref, description=p.label, observed_value=p.support_windows)
            for p in patterns
        ) or (Evidence(artifact_id=model_ref, description="regimes", observed_value=k),)
        finding = Finding(
            finding_id=finding_id(idk, input_hash), identity_key=idk,
            finding_type=FindingType.OPERATING_REGIME_DISCOVERED, category=FindingCategory.ANOMALY,
            scope=FindingScope.EQUIPMENT, origin=FindingOrigin.LEARNED,
            summary=f"{len(patterns)} operating regimes discovered (hypothesis)",
            detail="Regimes: " + "; ".join(p.label for p in patterns),
            target_key=features.unit, equipment_key=features.unit, severity=Severity.INFO,
            confidence=Confidence(
                value=round(health.coverage_pct / 100, 4),
                rationale="regime discovery over covered windows",
            ),
            evidence=evidence, source_engine=model_ref,
            observed_window=ObservedWindow(
                start=features.window_starts[0], end=features.window_ends[-1]
            ),
            provenance=Provenance(
                engine="pattern_learning", engine_version=self.version,
                source_unit=features.unit, input_hash=input_hash, produced_at=now_utc(),
            ),
        )
        return PatternResult(
            unit=features.unit, model_id=self.name, model_version=self.version,
            findings=(finding,), patterns=tuple(patterns), model_health=health,
        )
