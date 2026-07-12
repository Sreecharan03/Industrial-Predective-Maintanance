"""Grounded LLM communication layer (ADR-018).

A pluggable, citation-enforced narration layer over the frozen engineering
evidence. Provider-independent: the deterministic stub backs CI; Groq (or any
provider) plugs in behind the same LanguageModel interface.
"""

from senseminds.llm.base import LanguageModel
from senseminds.llm.factory import build_language_model
from senseminds.llm.grounding import CitationValidator
from senseminds.llm.models import (
    EvidenceBundle,
    EvidenceCategory,
    EvidenceItem,
    GroundedAnswer,
    GroundedClaim,
)
from senseminds.llm.prompt import PromptBuilder
from senseminds.llm.retrieval import EvidenceRetriever
from senseminds.llm.service import LlmQueryService
from senseminds.llm.stub import DeterministicStubModel

__all__ = [
    "CitationValidator",
    "DeterministicStubModel",
    "build_language_model",
    "EvidenceBundle",
    "EvidenceCategory",
    "EvidenceItem",
    "EvidenceRetriever",
    "GroundedAnswer",
    "GroundedClaim",
    "LanguageModel",
    "LlmQueryService",
    "PromptBuilder",
]
