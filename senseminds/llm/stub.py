"""Deterministic stub model (ADR-018).

A provider-free LanguageModel that grounds itself from the prompt's embedded
evidence block. It never invents: one cited claim per evidence item, and an
explicit "insufficient evidence" answer when the bundle is empty. This is what
lets every grounding / citation / hallucination test run offline in CI.
"""

from __future__ import annotations

import json
from typing import ClassVar

from senseminds.llm.base import LanguageModel
from senseminds.llm.prompt import extract_evidence


class DeterministicStubModel(LanguageModel):
    """Echoes the supplied evidence as grounded, cited claims - no NLP, no network."""

    name: ClassVar[str] = "stub"

    def complete(self, system: str, user: str) -> str:
        evidence = extract_evidence(user)
        if not evidence:
            return json.dumps({
                "answer": "Insufficient evidence to answer for this asset.",
                "claims": [],
                "insufficient": ["No grounded evidence was retrieved."],
            })
        claims = [
            {"text": e["text"], "category": e["category"], "citations": [e["ref"]]}
            for e in evidence
        ]
        answer = " ".join(e["text"] for e in evidence)
        return json.dumps({"answer": answer, "claims": claims, "insufficient": []})
