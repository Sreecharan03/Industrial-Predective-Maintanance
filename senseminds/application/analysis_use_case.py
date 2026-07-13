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
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from senseminds.application.finding_delta import is_material_change
from senseminds.application.pipeline import DeterministicPipeline
from senseminds.engines.health import HealthEngine
from senseminds.findings import (
    Finding,
    FindingOrigin,
    FindingsAssembler,
    ObservedWindow,
)
from senseminds.forecasting import Forecaster
from senseminds.infrastructure.artifact_store.base import ArtifactStore
from senseminds.infrastructure.db import Database
from senseminds.infrastructure.logging import get_logger
from senseminds.infrastructure.repositories import AnalysisUnitOfWork
from senseminds.ingestion import TimeSeriesSource
from senseminds.knowledge_graph import KnowledgeGraphProjector
from senseminds.pattern_learning import (
    FeaturePipeline,
    IsolationForestNovelty,
    PatternProjector,
    RegimeClusterer,
)
from senseminds.pattern_learning.models import PatternResult
from senseminds.pattern_learning.registry import ModelMetadata
from senseminds.repositories.models import (
    EngineRun,
    Persona,
    Report,
    ReportType,
    RunStatus,
)
from senseminds.rules import DEFAULT_RULES, RuleContext, RuleEvaluator
from senseminds.rules.models import RuleDefinition

_log = get_logger(__name__)


@dataclass(frozen=True)
class AnalysisRunResult:
    """Outcome of one analysis request."""

    unit: str
    input_hash: str
    run_id: str | None
    finding_count: int          # conditions observed this run
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    replayed: bool = False      # a run for this input already existed (no-op)
    recorded: int = 0           # of those, how many were NEW or materially changed
    learned: bool = False       # whether the Phase-B models also ran


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
        learning_enabled: bool = True,
        learning_interval_minutes: int = 30,
    ) -> None:
        self._db = db
        self._artifacts = artifact_store
        self._source = source
        self._pipeline = DeterministicPipeline()
        self._health = HealthEngine()
        self._assembler = FindingsAssembler()
        self._evaluator = RuleEvaluator(rules)

        # Phase B: unsupervised + forecasting. Expensive (forecasting back-tests every
        # sensor), and about slow trends — so it runs on its own, slower cadence.
        self._learning_enabled = learning_enabled
        self._learning_interval = timedelta(minutes=learning_interval_minutes)
        self._features = FeaturePipeline()
        self._novelty = IsolationForestNovelty(seed=7)
        self._regimes = RegimeClusterer(seed=7)
        self._forecaster = Forecaster()

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

            # Phase B is throttled: it looks for slow trends, so it does not need to
            # run on every 30-second tick (and forecasting is far too costly to).
            learn = self._should_learn(uow, unit, started)
            learned_results: list[PatternResult] = []
            if learn:
                learned_results = self._learn(series, ctx)

            learned = tuple(f for r in learned_results for f in r.findings)
            findings = tuple(derived) + tuple(diagnosed) + learned

            # A condition that has not changed is NOT re-recorded. Findings are
            # append-only and finding_id is derived from the input hash, so without
            # this every tick would write a fresh row (and grow the graph's condition
            # nodes) for something that is still exactly as true as it was.
            existing = {f.identity_key: f for f in uow.findings.current(unit)}
            changed = tuple(
                f for f in findings if is_material_change(existing.get(f.identity_key), f)
            )

            artifact_ids = tuple(self._artifacts.save(r) for r in results)
            uow.assets.save(series.asset)
            uow.findings.add_many(changed)

            projector = KnowledgeGraphProjector(uow.graph)
            projector.seed_catalog(series.asset)
            projector.project_findings(
                tuple(f for f in changed if f.origin is not FindingOrigin.LEARNED)
            )

            if learned_results:
                pattern_projector = PatternProjector(uow.graph)
                changed_learned = {f.finding_id for f in changed}
                for result in learned_results:
                    pattern_projector.project(replace(
                        result,
                        findings=tuple(f for f in result.findings
                                       if f.finding_id in changed_learned),
                    ))
                    self._record_model(uow, result, started, window)

            uow.reports.save(self._daily_report(unit, input_hash, findings, started))

            uow.runs.complete(EngineRun(
                run_id=run_id, unit=unit, input_hash=input_hash, status=RunStatus.COMPLETED,
                started_at=started, finished_at=_now(), finding_count=len(findings),
                engine_versions={r.provenance.engine: r.provenance.engine_version
                                 for r in results},
                artifact_ids=artifact_ids,
                # Every condition observed, including the unchanged ones — this is what
                # lets "current" drop a condition once it clears.
                observed_identities=tuple(sorted({f.identity_key for f in findings})),
                learned=learn,
            ))
        # commit happens on context exit; an exception rolls the whole run back.
        return AnalysisRunResult(
            unit=unit, input_hash=input_hash, run_id=run_id,
            finding_count=len(findings), findings=findings,
            recorded=len(changed), learned=learn,
        )

    # ------------------------------ Phase B ------------------------------

    def _should_learn(self, uow: AnalysisUnitOfWork, unit: str, now: datetime) -> bool:
        if not self._learning_enabled:
            return False
        last = uow.runs.last_learned_at(unit)
        return last is None or (now - last) >= self._learning_interval

    def _learn(self, series: object, ctx: object) -> list[PatternResult]:  # noqa: ANN001
        """Novelty + regimes + forecasts. Failures here must never fail the run:
        these are advisory hypotheses, not facts the plant depends on."""
        out: list[PatternResult] = []
        try:
            features = self._features.build(series)  # type: ignore[arg-type]
            out.append(self._novelty.run(features))
            out.append(self._regimes.run(features))
        except Exception:
            _log.exception("pattern_learning_failed", extra={"unit": series.manifest.unit})  # type: ignore[attr-defined]
        try:
            out.append(self._forecaster.forecast_unit(series, series.asset))  # type: ignore[attr-defined]
        except Exception:
            _log.exception("forecasting_failed", extra={"unit": series.manifest.unit})  # type: ignore[attr-defined]
        return out

    @staticmethod
    def _record_model(
        uow: AnalysisUnitOfWork, result: PatternResult, at: datetime, window: ObservedWindow
    ) -> None:
        """Every learned output is traceable to the exact model version that made it."""
        uow.models.save(
            ModelMetadata(
                model_id=result.model_id, version=result.model_version, trained_at=at,
                training_window_start=window.start, training_window_end=window.end,
                feature_schema_version="1", seed=7,
            ),
            {"health": result.model_health.model_dump(mode="json")
             if result.model_health else None,
             "patterns": len(result.patterns)},
        )

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
