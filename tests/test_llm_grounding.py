"""Grounded LLM layer (ADR-018) - grounding, citations, hallucination safeguards.

Pure and offline: the deterministic stub + citation validator, no DB or network.
"""

from __future__ import annotations

import json

from senseminds.llm import (
    CitationValidator,
    DeterministicStubModel,
    EvidenceBundle,
    EvidenceCategory,
    EvidenceItem,
    GroundedAnswer,
    LanguageModel,
    LlmQueryService,
    PromptBuilder,
)


def _bundle(*items: EvidenceItem, question: str = "How is it?") -> EvidenceBundle:
    return EvidenceBundle(unit="SC-126", question=question, items=items)


_FACT = EvidenceItem(ref="f1", kind="finding", category=EvidenceCategory.FACT,
                     text="Discharge pressure is stable.", confidence=0.99)
_FORECAST = EvidenceItem(ref="f2", kind="finding", category=EvidenceCategory.FORECAST,
                         text="Oil pressure projected to approach limit in ~12h.", confidence=0.7)


def _answer(bundle: EvidenceBundle, model: LanguageModel, persona="re") -> GroundedAnswer:  # noqa: ANN001
    persona = "reliability_engineer" if persona == "re" else persona
    system, user = PromptBuilder().build(bundle, persona)
    return CitationValidator().validate(model.complete(system, user), bundle, persona)


class _FixedModel(LanguageModel):
    name = "fixed"

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def complete(self, system: str, user: str) -> str:
        return json.dumps(self._payload)


# ------------------------------ grounding -----------------------------

def test_stub_grounds_every_claim_with_a_real_citation() -> None:
    answer = _answer(_bundle(_FACT, _FORECAST), DeterministicStubModel())
    assert answer.claims
    valid = _bundle(_FACT, _FORECAST).ids()
    for claim in answer.claims:
        assert claim.citations  # every engineering claim cites
        assert set(claim.citations) <= valid  # only real evidence ids
    assert set(answer.citations) <= valid


def test_confidence_registers_stay_distinct() -> None:
    answer = _answer(_bundle(_FACT, _FORECAST), DeterministicStubModel())
    cats = {c.category for c in answer.claims}
    assert EvidenceCategory.FACT in cats and EvidenceCategory.FORECAST in cats  # not blended


# --------------------------- insufficient evidence --------------------

def test_empty_bundle_yields_explicit_insufficient() -> None:
    answer = _answer(_bundle(question="Is bearing 3 failing?"), DeterministicStubModel())
    assert answer.claims == ()
    assert answer.insufficient  # authorised "I don't know"
    assert "insufficient" in answer.answer.lower()


# ---------------------- hallucination safeguards ----------------------

def test_claim_citing_unknown_id_is_dropped() -> None:
    # model invents a citation that is not in the bundle -> claim removed
    model = _FixedModel({"answer": "The compressor bearing is failing.",
                         "claims": [{"text": "Bearing is failing.", "category": "diagnosis",
                                     "citations": ["ghost-id"]}],
                         "insufficient": []})
    answer = _answer(_bundle(_FACT), model)
    assert all("ghost-id" not in c.citations for c in answer.claims)
    # only claim was unsupported -> degrades to insufficient, free text suppressed
    assert answer.claims == ()
    assert "failing" not in answer.answer.lower()


def test_uncited_claim_is_dropped() -> None:
    model = _FixedModel({"answer": "x", "claims": [
        {"text": "Grounded.", "category": "fact", "citations": ["f1"]},
        {"text": "Unsupported assertion.", "category": "fact", "citations": []},
    ], "insufficient": []})
    answer = _answer(_bundle(_FACT), model)
    texts = [c.text for c in answer.claims]
    assert "Grounded." in texts
    assert "Unsupported assertion." not in texts  # no citation -> dropped


def test_unparseable_output_degrades_safely() -> None:
    class _Garbage(LanguageModel):
        name = "garbage"

        def complete(self, system: str, user: str) -> str:
            return "not json at all"

    answer = _answer(_bundle(_FACT), _Garbage())
    assert answer.claims == ()
    assert answer.insufficient


# ------------------------------ personas ------------------------------

def test_persona_invariance_of_cited_ids() -> None:
    # same evidence, different personas -> identical set of cited ids
    bundle = _bundle(_FACT, _FORECAST)
    ids_by_persona = {
        p: set(_answer(bundle, DeterministicStubModel(), p).citations)
        for p in ("operator", "reliability_engineer", "executive")
    }
    assert len({frozenset(v) for v in ids_by_persona.values()}) == 1  # evidence-invariant


def test_service_answer_bundle_end_to_end() -> None:
    svc = LlmQueryService(retriever=None, model=DeterministicStubModel())  # type: ignore[arg-type]
    answer = svc.answer_bundle(_bundle(_FACT, _FORECAST), persona="operator")
    assert answer.persona == "operator"
    assert answer.claims and set(answer.citations) == {"f1", "f2"}
