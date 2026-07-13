"""Grounded LLM query service (ADR-018).

Orchestrates one grounded answer: retrieve evidence -> assemble prompt -> call the
pluggable model -> validate citations. All safety is in the framework around the
model; the model only narrates. Conversation memory (if added) influences only
presentation and re-retrieves fresh evidence each turn - it never mutates state.
"""

from __future__ import annotations

from senseminds.llm.base import LanguageModel
from senseminds.llm.grounding import CitationValidator
from senseminds.llm.models import EvidenceBundle, GroundedAnswer
from senseminds.llm.prompt import PromptBuilder
from senseminds.llm.retrieval import EvidenceRetriever

_DEFAULT_PERSONA = "reliability_engineer"


class LlmQueryService:
    """Answer a natural-language question about an asset, grounded and cited."""

    def __init__(
        self,
        retriever: EvidenceRetriever,
        model: LanguageModel,
        prompt_builder: PromptBuilder | None = None,
        validator: CitationValidator | None = None,
    ) -> None:
        self._retriever = retriever
        self._model = model
        self._prompt = prompt_builder or PromptBuilder()
        self._validator = validator or CitationValidator()

    @property
    def model_name(self) -> str:
        return self._model.name

    def answer(
        self,
        unit: str,
        question: str = "",
        persona: str = _DEFAULT_PERSONA,
        history: list[tuple[str, str]] | None = None,
    ) -> GroundedAnswer:
        bundle = self._retriever.retrieve(unit, question)
        return self.answer_bundle(bundle, persona, history)

    def answer_bundle(
        self,
        bundle: EvidenceBundle,
        persona: str = _DEFAULT_PERSONA,
        history: list[tuple[str, str]] | None = None,
    ) -> GroundedAnswer:
        system, user = self._prompt.build(bundle, persona, history)
        raw = self._model.complete(system, user)
        return self._validator.validate(raw, bundle, persona)
