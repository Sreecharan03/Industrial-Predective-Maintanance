"""Evidence retrieval (ADR-018 §2).

Builds a curated, read-only EvidenceBundle from the frozen stores - persisted
findings (DERIVED facts, DIAGNOSED diagnoses, LEARNED hypotheses/forecasts). It
touches no raw telemetry: every item is an already-attributed finding, cited by
finding_id. The knowledge graph and artifacts remain reachable through the same
read seam if richer retrieval is needed later.
"""

from __future__ import annotations

from senseminds.findings import Finding, FindingOrigin, FindingType
from senseminds.infrastructure.db import Database
from senseminds.infrastructure.repositories import UnitOfWork
from senseminds.llm.models import EvidenceBundle, EvidenceCategory, EvidenceItem


def _category(finding: Finding) -> EvidenceCategory:
    if finding.origin is FindingOrigin.DIAGNOSED:
        return EvidenceCategory.DIAGNOSIS
    if finding.origin is FindingOrigin.LEARNED:
        if finding.finding_type is FindingType.FORECAST_THRESHOLD_APPROACH:
            return EvidenceCategory.FORECAST
        return EvidenceCategory.HYPOTHESIS
    return EvidenceCategory.FACT


class EvidenceRetriever:
    """Assemble the evidence bundle for one asset/question from persisted findings."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def retrieve(self, unit: str, question: str = "") -> EvidenceBundle:
        with UnitOfWork(self._db) as uow:
            findings = uow.findings.for_unit(unit)
        items = tuple(
            EvidenceItem(
                ref=f.finding_id, kind="finding", category=_category(f),
                text=f.summary, detail=_first_sentences(f.detail),
                severity=f.severity.value, confidence=f.confidence.value,
            )
            for f in findings
        )
        return EvidenceBundle(unit=unit, question=question, items=items)


def _first_sentences(detail: str, limit: int = 2) -> str:
    """The leading sentences of a finding's rationale - carries the correct
    interpretation (e.g. 'Not evidence of a fault.') the narrator must respect."""
    parts = [s.strip() for s in detail.replace("\n", " ").split(". ") if s.strip()]
    return ". ".join(parts[:limit]).strip()
