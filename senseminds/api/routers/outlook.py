"""Predictive outlook — the forward-looking summary for one machine.

Every number here is lifted from a recorded finding; nothing is modelled in this
router. Specifically it does NOT report failure probability or remaining useful
life: both require labelled failure history the plant does not have yet (ADR-007
Phase C). What it CAN honestly report is how far the machine is from its limits
now (deterministic health), how long until a sensor is projected to reach a
limit at the current trend (the backtest-selected forecaster), and whether
behaviour is unlike history (unsupervised novelty) — each with the real model
name and its measured error, so the confidence shown is one that was actually
computed rather than asserted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from senseminds.api.deps import AppState, require_roles, state
from senseminds.domain.enums import Severity
from senseminds.findings import Finding, FindingType
from senseminds.infrastructure.repositories import UnitOfWork

router = APIRouter(tags=["outlook"])

_ENGINEER = ("maintenance_engineer", "reliability_engineer")

# How the forecaster's horizon steps translate to wall-clock (1 step = 1 hour).
_HOURS_PER_STEP = 1.0


class ForecastOutlook(BaseModel):
    sensor: str
    hours_ahead: float
    bound: float | None
    projected_value: float | None
    model_name: str          # the model the backtest actually selected
    model_version: str
    backtest_mae: float | None
    interval_confidence: float   # measured interval coverage, not a guess
    summary: str
    finding_id: str


class NoveltyOutlook(BaseModel):
    score: float
    windows: int
    top_features: list[dict]
    model_name: str
    finding_id: str


class OutlookResponse(BaseModel):
    unit: str
    display_name: str
    condition_score: float | None       # deterministic equipment health (0-100)
    condition_basis: str
    weakest_subsystem: dict | None
    soonest: ForecastOutlook | None     # the nearest projected limit approach
    forecasts: list[ForecastOutlook]
    novelty: NoveltyOutlook | None
    critical_count: int
    headline: str                       # plain-English one-liner for the card
    caveat: str                         # what this number is NOT
    recommendation: str
    recommendation_citations: list[str]


def _evidence_value(finding: Finding, needle: str) -> float | None:
    for e in finding.evidence:
        if needle in e.description and isinstance(e.observed_value, int | float):
            return float(e.observed_value)
    return None


def _model_id(finding: Finding) -> tuple[str, str]:
    """'forecast:seasonal_naive@0.1.0' -> ('seasonal_naive', '0.1.0')."""
    for e in finding.evidence:
        if "@" in e.artifact_id and ":" in e.artifact_id:
            ref = e.artifact_id.split(":", 1)[1]
            name, _, version = ref.partition("@")
            return name, version or "unknown"
    return finding.source_engine, "unknown"


def _forecast(finding: Finding) -> ForecastOutlook:
    name, version = _model_id(finding)
    steps = _evidence_value(finding, "lead-time steps") or 0.0
    return ForecastOutlook(
        sensor=finding.target_key,
        hours_ahead=round(steps * _HOURS_PER_STEP, 1),
        bound=_evidence_value(finding, "bound approached"),
        projected_value=_evidence_value(finding, "forecast mean"),
        model_name=name,
        model_version=version,
        backtest_mae=_evidence_value(finding, "backtest MAE"),
        interval_confidence=round(float(finding.confidence.value), 4),
        summary=finding.summary,
        finding_id=finding.finding_id,
    )


def _novelty(finding: Finding) -> NoveltyOutlook:
    name, _ = _model_id(finding)
    features = [
        {"feature": e.description.replace("contributing feature ", ""),
         "deviation": float(e.observed_value)}
        for e in finding.evidence
        if e.description.startswith("contributing feature")
        and isinstance(e.observed_value, int | float)
    ]
    windows = 0
    for token in finding.summary.split():
        if token.isdigit():
            windows = int(token)
            break
    return NoveltyOutlook(
        score=round(float(_evidence_value(finding, "novelty score") or 0.0), 4),
        windows=windows,
        top_features=features[:3],
        model_name=name,
        finding_id=finding.finding_id,
    )


def _build(unit: str, display_name: str, findings: list[Finding]) -> OutlookResponse:
    by_type: dict[FindingType, list[Finding]] = {}
    for f in findings:
        by_type.setdefault(f.finding_type, []).append(f)

    # Deterministic condition: equipment-level health, and the weakest subsystem.
    condition: float | None = None
    weakest: dict | None = None
    for f in by_type.get(FindingType.HEALTH_DEGRADED, []):
        score = _evidence_value(f, "health score")
        if score is None:
            continue
        if f.scope.value == "equipment":
            condition = score
        elif f.subsystem_key and (weakest is None or score < weakest["score"]):
            weakest = {"key": f.subsystem_key, "score": score}

    forecasts = sorted(
        (_forecast(f) for f in by_type.get(FindingType.FORECAST_THRESHOLD_APPROACH, [])),
        key=lambda x: x.hours_ahead,
    )
    soonest = forecasts[0] if forecasts else None

    novelty_findings = by_type.get(FindingType.NOVELTY_ELEVATED, [])
    novelty = _novelty(novelty_findings[0]) if novelty_findings else None

    criticals = [f for f in findings if f.severity is Severity.CRITICAL]

    # Headline: the most decision-relevant true statement, in that order.
    if criticals:
        headline = (
            f"{len(criticals)} condition{'s' if len(criticals) != 1 else ''} "
            "past a safe limit right now — act on those before anything forecast."
        )
    elif soonest:
        headline = (
            f"{soonest.sensor.replace('_', ' ')} is trending toward its limit "
            f"in about {soonest.hours_ahead:g} hour"
            f"{'s' if soonest.hours_ahead != 1 else ''} if nothing changes."
        )
    elif novelty:
        headline = "Nothing is approaching a limit, but behaviour is unlike this machine's history."
    else:
        headline = "No limit approach projected and behaviour matches this machine's history."

    caveat = (
        "This is a trend projection against operating limits — not a failure prediction. "
        "Remaining useful life needs labelled breakdown history, which is not yet available."
    )

    parts: list[str] = []
    citations: list[str] = []
    if criticals:
        parts.append(
            f"Deal with the {len(criticals)} critical condition"
            f"{'s' if len(criticals) != 1 else ''} first: "
            + "; ".join(f.summary for f in criticals[:2])
        )
        citations += [f.finding_id for f in criticals[:2]]
    if soonest:
        bound = f" (limit {soonest.bound:g})" if soonest.bound is not None else ""
        parts.append(
            f"Watch {soonest.sensor.replace('_', ' ')}{bound} — the "
            f"{soonest.model_name} forecast reaches it in ~{soonest.hours_ahead:g}h"
        )
        citations.append(soonest.finding_id)
    if novelty and novelty.top_features:
        drivers = ", ".join(f["feature"].replace("_", " ") for f in novelty.top_features)
        parts.append(f"Behaviour differs from history, driven by: {drivers}")
        citations.append(novelty.finding_id)
    if weakest:
        parts.append(
            f"Weakest subsystem is {weakest['key'].replace('_', ' ')} at {weakest['score']:g}%"
        )
    if not parts:
        parts.append("No action indicated — limits, trends and behaviour all look normal")

    return OutlookResponse(
        unit=unit,
        display_name=display_name,
        condition_score=condition,
        condition_basis="Deterministic health score from measured readings (not a model output).",
        weakest_subsystem=weakest,
        soonest=soonest,
        forecasts=forecasts,
        novelty=novelty,
        critical_count=len(criticals),
        headline=headline,
        caveat=caveat,
        recommendation=". ".join(parts) + ".",
        recommendation_citations=citations,
    )


@router.get("/assets/{unit}/outlook", response_model=OutlookResponse,
            dependencies=[Depends(require_roles(*_ENGINEER))])
def outlook(unit: str, app: AppState = Depends(state)) -> OutlookResponse:
    with UnitOfWork(app.db) as uow:
        asset = uow.assets.get(unit)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"unknown unit {unit!r}")
        findings = uow.findings.current(unit)
    return _build(unit, asset.display_name, findings)
