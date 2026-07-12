"""Pattern Learning (Phase B) - label-free unsupervised hypotheses.

Reads validated data + engineering facts; writes only LEARNED hypotheses. Never
produces facts, never contaminates the deterministic pipeline (ADR-016).
"""

from senseminds.pattern_learning.base import PatternModel, model_health
from senseminds.pattern_learning.clustering import RegimeClusterer
from senseminds.pattern_learning.features import FeaturePipeline
from senseminds.pattern_learning.feedback import (
    FeedbackRepository,
    FeedbackVerdict,
    HumanFeedback,
    InMemoryFeedbackRepository,
)
from senseminds.pattern_learning.models import (
    DiscoveredPattern,
    FeatureFrame,
    ModelHealth,
    PatternLifecycle,
    PatternResult,
)
from senseminds.pattern_learning.novelty import IsolationForestNovelty
from senseminds.pattern_learning.projector import PatternProjector
from senseminds.pattern_learning.registry import (
    InMemoryModelRegistry,
    ModelMetadata,
    ModelRegistry,
)

__all__ = [
    "DiscoveredPattern",
    "FeatureFrame",
    "FeaturePipeline",
    "FeedbackRepository",
    "FeedbackVerdict",
    "HumanFeedback",
    "InMemoryFeedbackRepository",
    "InMemoryModelRegistry",
    "IsolationForestNovelty",
    "ModelHealth",
    "ModelMetadata",
    "ModelRegistry",
    "PatternLifecycle",
    "PatternModel",
    "PatternProjector",
    "PatternResult",
    "RegimeClusterer",
    "model_health",
]
