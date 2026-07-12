"""Application layer - use-cases orchestrating domain + engines.

Holds the deterministic pipeline and the `AnalysisContext` bundle that fan-in
consumers (Health, Rules) depend on.
"""

from senseminds.application.context import AnalysisContext, MissingDependencyError
from senseminds.application.pipeline import DeterministicPipeline

__all__ = ["AnalysisContext", "DeterministicPipeline", "MissingDependencyError"]
