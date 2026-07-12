"""Analysis use case (ADR-019 D5).

Orchestrates one asset's complete deterministic analysis and persists the result
as a single atomic unit of work. The engines, findings assembler, rule engine,
and knowledge-graph projector stay entirely transaction-unaware; all transaction
management lives here (and in the AnalysisUnitOfWork).

Flow: **compute** the whole pipeline purely (no DB, no transaction), then open
**one** AnalysisUnitOfWork and persist findings + KG projection + report + engine
artifacts + the engine-run record together. Either everything commits or nothing
does. Re-running the same input is idempotent: the (unit, input_hash) run record
gates duplicate work, and findings / graph writes are independently idempotent.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from senseminds.application.pipeline import DeterministicPipeline
from senseminds.engines.health import HealthEngine
from senseminds.findings import Finding, FindingsAssembler, ObservedWindow
from senseminds.infrastructure.artifact_store.base import ArtifactStore
from senseminds.infrastructure.db import Database
from senseminds.infrastructure.repositories import AnalysisUnitOfWork
from senseminds.ingestion import TimeSeriesSource
from senseminds.knowledge_graph import KnowledgeGraphProjector
from senseminds.repositories.models import (
    EngineRun,
    Persona,
    Report,
    ReportType,
    RunStatus,
)
from senseminds.rules import DEFAULT_RULES, RuleContext, RuleEvaluator
from senseminds.rules.models import RuleDefinition


@dataclass(frozen=True)
class AnalysisRunResult:
    """Outcome of one analysis request."""

    unit: str
    input_hash: str
    run_id: str | None
    finding_count: int
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    replayed: bool = False  # True if a run for this input already existed (no-op)


def _now() -> datetime:
    return datetime.now(tz=UTC)


class AnalysisUseCase:
    """Run and durably persist one asset's analysis atomically."""

    def __init__(
        self,
        db: Database,
        artifact_store: ArtifactStore,
        source: TimeSeriesSource,
        rules: tuple[RuleDefinition, ...] = DEFAULT_RULES,
    ) -> None:
        self._db = db
        self._artifacts = artifact_store
        self._source = source
        self._pipeline = DeterministicPipeline()
        self._health = HealthEngine()
        self._assembler = FindingsAssembler()
        self._evaluator = RuleEvaluator(rules)

    def run(self, unit: str) -> AnalysisRunResult:
        # ---- compute: pure, no DB, no transaction (ADR-019 §7) ----
        series = self._source.load(unit)
        ctx = self._pipeline.run(series)
        health = self._health.compute(ctx)
        input_hash = ctx.statistics.provenance.input_hash
        window = ObservedWindow(start=series.manifest.start, end=series.manifest.end)
        subsystem_of = {k: sub.key for sub in series.asset.subsystems for k in sub.sensor_keys}

        derived = self._assembler.assemble(
            threshold=ctx.threshold, reliability=ctx.reliability, health=health,
            observed_window=window, subsystem_of=subsystem_of,
        )
        rule_ctx = RuleContext(
            unit=unit, equipment_class=series.asset.equipment_class.value,
            input_hash=input_hash, observed_window=window, subsystem_of=subsystem_of,
        )
        diagnosed = self._evaluator.evaluate(derived, rule_ctx)
        findings = tuple(derived) + tuple(diagnosed)
        results = (ctx.quality, ctx.statistics, ctx.operating_state, ctx.envelope,
                   ctx.threshold, ctx.timeline, ctx.reliability, health)

        # ---- persist: one atomic transaction over every store ----
        run_id = uuid.uuid4().hex
        started = _now()
        with AnalysisUnitOfWork(self._db) as uow:
            owns = uow.runs.begin(EngineRun(
                run_id=run_id, unit=unit, input_hash=input_hash,
                status=RunStatus.RUNNING, started_at=started,
            ))
            if not owns:
                # a run for this exact input already exists -> idempotent no-op.
                return AnalysisRunResult(unit=unit, input_hash=input_hash, run_id=None,
                                         finding_count=0, replayed=True)

            artifact_ids = tuple(self._artifacts.save(r) for r in results)
            uow.assets.save(series.asset)
            uow.findings.add_many(findings)

            projector = KnowledgeGraphProjector(uow.graph)
            projector.seed_catalog(series.asset)
            projector.project_findings(findings)

            uow.reports.save(self._daily_report(unit, input_hash, findings, started))

            uow.runs.complete(EngineRun(
                run_id=run_id, unit=unit, input_hash=input_hash, status=RunStatus.COMPLETED,
                started_at=started, finished_at=_now(), finding_count=len(findings),
                engine_versions={r.provenance.engine: r.provenance.engine_version for r in results},
                artifact_ids=artifact_ids,
            ))
        # commit happens on context exit; an exception rolls the whole run back.
        return AnalysisRunResult(unit=unit, input_hash=input_hash, run_id=run_id,
                                 finding_count=len(findings), findings=findings)

    @staticmethod
    def _daily_report(
        unit: str, input_hash: str, findings: tuple[Finding, ...], at: datetime
    ) -> Report:
        by_severity = Counter(f.severity.value for f in findings)
        by_origin = Counter(f.origin.value for f in findings)
        return Report(
            report_id=f"{unit}:{input_hash}:daily",  # deterministic -> idempotent
            report_type=ReportType.DAILY_ASSET_HEALTH, persona=Persona.RELIABILITY_ENGINEER,
            unit=unit, requested_at=at,
            cited_finding_ids=tuple(sorted(f.finding_id for f in findings)),
            payload={"finding_count": len(findings),
                     "by_severity": dict(by_severity), "by_origin": dict(by_origin)},
        )
