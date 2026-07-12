"""Prompt assembly (ADR-018 §3).

Lays out evidence in five explicitly separated registers (Facts / Diagnoses /
Hypotheses / Forecasts / Insufficient) and instructs the model to answer ONLY
from that evidence, citing ``ref`` ids, and to return a strict JSON contract. A
machine-readable ``<EVIDENCE_JSON>`` block lets the deterministic stub ground
itself without any NLP; a real model reads the whole prompt as context.
"""

from __future__ import annotations

import json

from senseminds.llm.models import EvidenceBundle, EvidenceCategory

EVIDENCE_START = "<EVIDENCE_JSON>"
EVIDENCE_END = "</EVIDENCE_JSON>"

_PERSONA_STYLE = {
    "operator": "a plant operator: plain, immediate, what to watch now",
    "maintenance_engineer": "a maintenance engineer: procedural, diagnosed conditions and actions",
    "reliability_engineer": "a reliability engineer: analytical, evidence chains + uncertainty",
    "plant_manager": "a plant manager: asset-level risk, priorities, lead times",
    "executive": "an executive: brief, outcome-oriented, material risks only",
}

_CATEGORY_TITLE = {
    EvidenceCategory.FACT: "ENGINEERING FACTS (deterministic, certain)",
    EvidenceCategory.DIAGNOSIS: "DIAGNOSED FINDINGS (rule confidence)",
    EvidenceCategory.HYPOTHESIS: "LEARNED HYPOTHESES (pattern confidence, unconfirmed)",
    EvidenceCategory.FORECAST: "FORECASTS (advisory, interval-bounded)",
}

_SYSTEM = """You are SenseMinds 360's communication layer for industrial refrigeration and \
utility equipment (screw compressors, air and nitrogen plants) in a pharmaceutical plant. \
You do NOT analyse data. Deterministic engines have already produced the evidence; your \
only job is to explain that evidence faithfully for a specific audience.

ABSOLUTE RULES
1. GROUND EVERYTHING. Every engineering statement - in your claims AND in your prose \
answer - must be supported by the supplied evidence and cite the ref id(s) it comes from. \
If something is not in the evidence, you do not say it. Prefer each item's DETAIL text for \
the correct interpretation.
2. NEVER ESCALATE. A "threshold mis-specified" or "threshold config review" finding means \
the supplied limit does not match how the machine actually operates - it is a CONFIGURATION \
or DATA issue for engineering review and is explicitly NOT evidence of a fault, degradation, \
or an imminent breach. Do not call such a machine "unhealthy", "failing", or "at risk" on \
that basis. Report what each finding actually says, at its stated severity.
3. KEEP REGISTERS DISTINCT; never merge their certainty:
   - FACT: measured/deterministic - state plainly.
   - DIAGNOSIS: rule-derived - "diagnosed (confidence ...)".
   - HYPOTHESIS / FORECAST: advisory and unconfirmed - "a learned hypothesis", "projected ... \
(advisory)". Only say a limit is being approached if a FORECAST item says so.
4. NO INVENTION. Never introduce a failure mode, root cause, prediction, severity, or \
maintenance action that is not present in the evidence. Recommendations may only be repeated \
from evidence, never authored.
5. The "answer" must be a faithful synthesis of your cited claims ONLY - it may contain no \
assertion that is not backed by a claim. If evidence does not cover part of the question, put \
that gap in "insufficient" rather than guessing. If there is no evidence at all, the answer is \
that there is insufficient evidence.

Return STRICT JSON only: {"answer": str, "claims": [{"text": str, "category": \
"fact|diagnosis|hypothesis|forecast", "citations": [ref,...]}], "insufficient": [str,...]}"""


class PromptBuilder:
    """Assemble the (system, user) prompt for one grounded question."""

    def build(self, bundle: EvidenceBundle, persona: str) -> tuple[str, str]:
        style = _PERSONA_STYLE.get(persona, _PERSONA_STYLE["reliability_engineer"])
        question = bundle.question or "Summarise the current state of this asset."
        lines = [
            f"Asset: {bundle.unit}",
            f"Audience: write for {style}.",
            f"Question: {question}",
            "",
        ]
        for category in EvidenceCategory:
            items = bundle.by_category(category)
            lines.append(f"## {_CATEGORY_TITLE[category]}")
            if items:
                for i in items:
                    sev = f" severity={i.severity}" if i.severity else ""
                    conf = f" confidence={i.confidence}" if i.confidence is not None else ""
                    lines.append(f"- [{i.ref}]{sev}{conf} {i.text}")
                    if i.detail:
                        lines.append(f"    interpretation: {i.detail}")
            else:
                lines.append("- (none)")
            lines.append("")
        if not bundle.items:
            lines.append("No evidence was retrieved for this question.")
            lines.append("")

        # Machine-readable evidence for deterministic grounding.
        payload = [
            {"ref": i.ref, "category": i.category.value,
             "text": i.text + (f" ({i.detail})" if i.detail else "")}
            for i in bundle.items
        ]
        lines.append(EVIDENCE_START + json.dumps(payload) + EVIDENCE_END)
        return _SYSTEM, "\n".join(lines)


def extract_evidence(user_prompt: str) -> list[dict]:
    """Parse the embedded evidence block (used by the deterministic stub)."""
    start = user_prompt.find(EVIDENCE_START)
    end = user_prompt.find(EVIDENCE_END)
    if start == -1 or end == -1:
        return []
    return json.loads(user_prompt[start + len(EVIDENCE_START):end])
