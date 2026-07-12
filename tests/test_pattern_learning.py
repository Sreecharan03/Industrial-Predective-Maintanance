"""Pattern Learning (Phase B) - behaviour, reproducibility, boundary isolation,
model health, human feedback, and KG hypothesis projection."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from senseminds.findings import FindingCategory, FindingOrigin, FindingType
from senseminds.ingestion import ProcessedCsvSource
from senseminds.knowledge_graph import InMemoryKnowledgeGraph, NodeType
from senseminds.knowledge_graph.projector import condition_id
from senseminds.pattern_learning import (
    FeaturePipeline,
    FeedbackVerdict,
    HumanFeedback,
    InMemoryFeedbackRepository,
    IsolationForestNovelty,
    PatternProjector,
    RegimeClusterer,
)


def _series(tmp_path: Path, values: dict[str, list]):  # noqa: ANN202
    n = len(next(iter(values.values())))
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame({"timestamp": [t.isoformat() for t in ts], **values}).to_csv(
        tmp_path / "SC-126.csv", index=False
    )
    return ProcessedCsvSource(tmp_path).load("SC-126")


def _anomalous(tmp_path: Path):  # noqa: ANN202
    rng = np.random.default_rng(0)
    sp = list(17 + rng.normal(0, 0.3, 120))
    dp = list(210 + rng.normal(0, 1.0, 120))
    for i in range(50, 60):  # one clearly anomalous window
        sp[i] = 60.0
        dp[i] = 120.0
    return _series(tmp_path, {"Suction Pressure": sp, "Discharge Pressure": dp})


def _bimodal(tmp_path: Path):  # noqa: ANN202
    rng = np.random.default_rng(1)
    sp = list(12 + rng.normal(0, 0.3, 60)) + list(25 + rng.normal(0, 0.3, 60))
    return _series(tmp_path, {"Suction Pressure": sp})


# ----------------------------- behaviour -----------------------------

def test_feature_pipeline_is_deterministic(tmp_path: Path) -> None:
    series = _anomalous(tmp_path)
    a = FeaturePipeline(window_size=10).build(series)
    b = FeaturePipeline(window_size=10).build(series)
    assert np.array_equal(a.matrix, b.matrix)
    assert a.feature_names == b.feature_names


def test_novelty_detects_injected_anomaly(tmp_path: Path) -> None:
    features = FeaturePipeline(window_size=10).build(_anomalous(tmp_path))
    result = IsolationForestNovelty(seed=0, threshold=0.6).run(features)
    assert result.findings
    f = result.findings[0]
    assert f.finding_type is FindingType.NOVELTY_ELEVATED
    assert f.origin is FindingOrigin.LEARNED
    # explainable: contributing features are in the evidence (ADR-016 R4)
    assert any("contributing feature" in e.description for e in f.evidence)


def test_clustering_discovers_regimes(tmp_path: Path) -> None:
    features = FeaturePipeline(window_size=10).build(_bimodal(tmp_path))
    result = RegimeClusterer(seed=0, n_regimes=3).run(features)
    assert len(result.patterns) >= 2
    assert result.findings[0].finding_type is FindingType.OPERATING_REGIME_DISCOVERED
    assert all(p.lifecycle is not None for p in result.patterns)


# ----------------------------- reproducibility ------------------------

def test_novelty_is_reproducible(tmp_path: Path) -> None:
    features = FeaturePipeline(window_size=10).build(_anomalous(tmp_path))
    a = IsolationForestNovelty(seed=0).run(features)
    b = IsolationForestNovelty(seed=0).run(features)
    assert [f.finding_id for f in a.findings] == [f.finding_id for f in b.findings]
    assert a.findings[0].evidence[0].observed_value == b.findings[0].evidence[0].observed_value


# ----------------------------- boundary isolation ---------------------

def test_learned_outputs_are_learned_origin_only(tmp_path: Path) -> None:
    features = FeaturePipeline(window_size=10).build(_anomalous(tmp_path))
    nov = IsolationForestNovelty(seed=0).run(features)
    reg = RegimeClusterer(seed=0).run(FeaturePipeline(window_size=10).build(_bimodal(tmp_path)))
    for f in (*nov.findings, *reg.findings):
        assert f.origin is FindingOrigin.LEARNED  # never DERIVED/DIAGNOSED
        assert f.category is FindingCategory.ANOMALY
        assert f.provenance.engine == "pattern_learning"


def test_model_health_reports_and_is_reproducible(tmp_path: Path) -> None:
    features = FeaturePipeline(window_size=10).build(_anomalous(tmp_path))
    result = IsolationForestNovelty(seed=0).run(features)
    assert result.model_health is not None
    assert result.model_health.reproducible is True
    assert 0.0 <= result.model_health.coverage_pct <= 100.0


def test_insufficient_windows_yields_no_findings(tmp_path: Path) -> None:
    series = _series(tmp_path, {"Suction Pressure": [17.0] * 20})
    features = FeaturePipeline(window_size=10).build(series)  # only 2 windows
    result = IsolationForestNovelty(seed=0).run(features)
    assert result.findings == ()
    assert result.model_health is not None


# ----------------------------- human feedback -------------------------

def test_feedback_interface_stores_verdicts() -> None:
    repo = InMemoryFeedbackRepository()
    fb = HumanFeedback(
        finding_identity_key="idk1", verdict=FeedbackVerdict.FALSE_POSITIVE,
        author="engineer", note="known seasonal", created_at=datetime(2026, 7, 10, tzinfo=UTC),
    )
    repo.record(fb)
    assert repo.for_finding("idk1") == [fb]
    assert repo.for_finding("other") == []


# ----------------------------- KG projection --------------------------

def test_hypotheses_project_as_quarantined_nodes(tmp_path: Path) -> None:
    features = FeaturePipeline(window_size=10).build(_anomalous(tmp_path))
    result = IsolationForestNovelty(seed=0).run(features)
    repo = InMemoryKnowledgeGraph()
    proj = PatternProjector(repo)
    proj.project(result)
    proj.project(result)  # idempotent

    assert repo.nodes(NodeType.LEARNED_MODEL)
    patterns = repo.nodes(NodeType.DISCOVERED_PATTERN)
    assert patterns and patterns[0].properties["status"] == "hypothesis"
    # the learned finding-condition is marked origin=learned (separable from facts)
    cond = repo.get_node(condition_id(result.findings[0].identity_key))
    assert cond is not None and cond.properties["origin"] == "learned"
