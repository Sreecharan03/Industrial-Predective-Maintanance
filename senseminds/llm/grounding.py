"""Grounding & citation enforcement (ADR-018 §4/§6).

The safety frame that sits AROUND the model. It parses the model's JSON, then
mechanically drops every engineering claim whose citations are not all present in
the retrieved evidence bundle. A response reduced to no surviving claims degrades
to an explicit "insufficient evidence" answer rather than an unsupported one. The
model is never trusted to self-police - this validator is.
"""

from __future__ import annotations

import json

from senseminds.llm.models import (
    EvidenceBundle,
    EvidenceCategory,
    GroundedAnswer,
    GroundedClaim,
)

_INSUFFICIENT = "Insufficient evidence to answer this question for the asset."


class CitationValidator:
    """Turn a raw model completion into a validated, fully-cited GroundedAnswer."""

    def validate(
        self, raw: str, bundle: EvidenceBundle, persona: str
    ) -> GroundedAnswer:
        valid_ids = bundle.ids()
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return self._insufficient(bundle, persona, ["Model returned unparseable output."])

        claims: list[GroundedClaim] = []
        for raw_claim in parsed.get("claims", []) or []:
            claim = self._valid_claim(raw_claim, valid_ids)
            if claim is not None:
                claims.append(claim)

        insufficient = tuple(str(x) for x in (parsed.get("insufficient") or []))
        kind = str(parsed.get("kind") or "engineering").lower()

        if kind == "chat" and not claims:
            # A greeting or a question about the assistant itself. There is nothing to
            # cite and nothing to fabricate — reply plainly, with no claims.
            answer = str(parsed.get("answer") or "").strip()
            return GroundedAnswer(
                unit=bundle.unit, persona=persona,
                answer=answer or "How can I help with this machine?",
                claims=(), insufficient=(), citations=(),
            )

        if not claims:
            # An engineering question with nothing grounded behind it -> never emit
            # the model's free text.
            return self._insufficient(bundle, persona,
                                      list(insufficient) or ["No supported claims."])

        citations = tuple(sorted({c for claim in claims for c in claim.citations}))
        answer = str(parsed.get("answer") or "").strip() or " ".join(c.text for c in claims)
        return GroundedAnswer(
            unit=bundle.unit, persona=persona, answer=answer,
            claims=tuple(claims), insufficient=insufficient, citations=citations,
        )

    @staticmethod
    def _valid_claim(raw_claim: object, valid_ids: set[str]) -> GroundedClaim | None:
        if not isinstance(raw_claim, dict):
            return None
        text = str(raw_claim.get("text") or "").strip()
        citations = raw_claim.get("citations") or []
        if not text or not isinstance(citations, list) or not citations:
            return None  # an engineering claim MUST cite
        cited = tuple(str(c) for c in citations)
        if not set(cited) <= valid_ids:
            return None  # a citation to something not in the bundle is dropped
        try:
            category = EvidenceCategory(str(raw_claim.get("category")))
        except ValueError:
            category = EvidenceCategory.FACT
        return GroundedClaim(text=text, category=category, citations=cited)

    @staticmethod
    def _insufficient(
        bundle: EvidenceBundle, persona: str, reasons: list[str]
    ) -> GroundedAnswer:
        return GroundedAnswer(
            unit=bundle.unit, persona=persona, answer=_INSUFFICIENT,
            claims=(), insufficient=tuple(reasons), citations=(),
        )
