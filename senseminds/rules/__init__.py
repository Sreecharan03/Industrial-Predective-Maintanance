"""Rule Engine - deterministic reasoning over engineering knowledge.

Consumes findings/knowledge, produces DIAGNOSED findings. No analytics, no ML,
no LLM.
"""

from senseminds.rules.catalog import DEFAULT_RULES
from senseminds.rules.confidence import diagnosis_confidence
from senseminds.rules.evaluator import RuleContext, RuleEvaluator
from senseminds.rules.models import RuleDefinition, RuleKind, RuleScope

__all__ = [
    "DEFAULT_RULES",
    "RuleContext",
    "RuleDefinition",
    "RuleEvaluator",
    "RuleKind",
    "RuleScope",
    "diagnosis_confidence",
]
