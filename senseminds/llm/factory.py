"""Language-model selection (ADR-018).

One place decides the provider from config: a Groq key enables the real adapter;
its absence falls back to the deterministic stub, so the platform (and CI) runs
fully offline. Consumers depend only on the LanguageModel interface.
"""

from __future__ import annotations

from senseminds.config import Settings
from senseminds.llm.base import LanguageModel
from senseminds.llm.stub import DeterministicStubModel


def build_language_model(settings: Settings) -> LanguageModel:
    if settings.groq_api_key:
        from senseminds.llm.groq import GroqLanguageModel

        return GroqLanguageModel(settings.groq_api_key, model=settings.llm_model)
    return DeterministicStubModel()
