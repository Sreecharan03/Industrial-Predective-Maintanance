"""Rule Engine evaluator (ADR-015).

Deterministic, monotonic forward-chaining to a fixpoint. Rules are applied in a
total order (priority desc, rule_id asc); each pass fires every rule whose
co-located required findings are present (and excluded ones absent), producing
DIAGNOSED findings. Because findings are idempotent by identity_key and rules
only ADD findings, the fixpoint terminates when a pass yields no new identity;
a max-iteration bound is a safety net. Rules never mutate inputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from senseminds.domain.value_objects import Evidence, Provenance
from senseminds.findings import Finding, FindingOrigin, FindingScope, ObservedWindow
from senseminds.findings.identity import finding_id, identity_key
from senseminds.rules.confidence import diagnosis_confidence
from senseminds.rules.models import RuleDefinition

ENGINE_NAME = "rule_engine"
ENGINE_VERSION = "0.1.0"


@dataclass(frozen=True)
class RuleContext:
    """Light context a rule needs beyond the findings themselves."""

    unit: str
    equipment_class: str
    input_hash: str
    observed_window: ObservedWindow
    reliability: Mapping[str, float] = field(default_factory=dict)  # sensor_key -> trust
    subsystem_of: Mapping[str, str] = field(default_factory=dict)  # sensor_key -> subsystem


@dataclass(frozen=True)
class _Match:
    target_key: str
    triggers: tuple[Finding, ...]


class RuleEvaluator:
    """Reason over findings to produce DIAGNOSED findings (monotonic fixpoint)."""

    def __init__(self, rules: Sequence[RuleDefinition], max_iterations: int = 16) -> None:
        self._rules = sorted(
            (r for r in rules if r.enabled), key=lambda r: (-r.priority, r.rule_id)
        )
        self._max_iterations = max_iterations

    def evaluate(self, findings: Sequence[Finding], context: RuleContext) -> tuple[Finding, ...]:
        base = list(findings)
        produced: dict[str, Finding] = {}
        priority_of: dict[str, int] = {}

        for _ in range(self._max_iterations):
            current = base + list(produced.values())
            new_count = 0
            for rule in self._rules:
                if not self._applies(rule, context):
                    continue
                if self._blocked(rule, current):
                    continue
                for match in self._matches(rule, current):
                    f = self._diagnose(rule, match, context)
                    if f.identity_key not in produced:
                        produced[f.identity_key] = f
                        priority_of[f.identity_key] = rule.priority
                        new_count += 1
            if new_count == 0:
                break

        # conflict-resolution ranking: priority, then confidence, then severity
        ranked = sorted(
            produced.values(),
            key=lambda f: (
                -priority_of[f.identity_key],
                -f.confidence.value,
                -f.severity.rank,
                f.finding_id,
            ),
        )
        return tuple(ranked)

    # ------------------------------ matching ------------------------------
    @staticmethod
    def _applies(rule: RuleDefinition, ctx: RuleContext) -> bool:
        return (
            "*" in rule.applies_to
            or ctx.equipment_class in rule.applies_to
            or ctx.unit in rule.applies_to
        )

    @staticmethod
    def _blocked(rule: RuleDefinition, findings: list[Finding]) -> bool:
        present = {f.finding_type for f in findings}
        return any(t in present for t in rule.excluded_finding_types)

    def _matches(self, rule: RuleDefinition, findings: list[Finding]) -> list[_Match]:
        required = set(rule.required_finding_types)
        wanted = required | set(rule.optional_finding_types)
        if rule.match_scope is FindingScope.SENSOR:
            groups: dict[str, list[Finding]] = {}
            for f in findings:
                if f.scope is FindingScope.SENSOR:
                    groups.setdefault(f.target_key, []).append(f)
            matches = []
            for target, group in sorted(groups.items()):
                present = {f.finding_type for f in group}
                if required <= present:
                    triggers = tuple(
                        sorted(
                            (f for f in group if f.finding_type in wanted),
                            key=lambda f: f.finding_id,
                        )
                    )
                    matches.append(_Match(target_key=target, triggers=triggers))
            return matches
        # EQUIPMENT / PLANT scope: correlate across the whole unit
        present = {f.finding_type for f in findings}
        if required <= present:
            triggers = tuple(
                sorted(
                    (f for f in findings if f.finding_type in wanted), key=lambda f: f.finding_id
                )
            )
            return [_Match(target_key=self._equipment_target(rule, findings), triggers=triggers)]
        return []

    @staticmethod
    def _equipment_target(rule: RuleDefinition, findings: list[Finding]) -> str:
        return findings[0].equipment_key if findings else "unknown"

    # ------------------------------ diagnosis ------------------------------
    def _diagnose(self, rule: RuleDefinition, match: _Match, ctx: RuleContext) -> Finding:
        scope = rule.match_scope
        target = match.target_key
        idk = identity_key(ctx.unit, rule.produced_finding_type, scope, target)
        fid = finding_id(idk, ctx.input_hash)

        sensors = {t.target_key for t in match.triggers if t.scope is FindingScope.SENSOR}
        reliability_factor = min((ctx.reliability.get(s, 1.0) for s in sensors), default=1.0)
        conf = diagnosis_confidence(
            rule.rule_confidence, [t.confidence.value for t in match.triggers], reliability_factor
        )
        evidence = tuple(
            Evidence(
                artifact_id=f"finding:{t.finding_id}",
                description=f"triggered by {t.finding_type.value}: {t.summary}",
                observed_value=None,
            )
            for t in match.triggers
        )
        subsystem_key = ctx.subsystem_of.get(target) if scope is FindingScope.SENSOR else None
        return Finding(
            finding_id=fid,
            identity_key=idk,
            finding_type=rule.produced_finding_type,
            category=rule.produced_category,
            scope=scope,
            origin=FindingOrigin.DIAGNOSED,
            summary=f"{rule.description} ({scope.value}:{target})",
            detail="; ".join(rule.engineering_assumptions) or rule.description,
            target_key=target,
            equipment_key=ctx.unit,
            subsystem_key=subsystem_key,
            severity=rule.produced_severity,
            confidence=conf,
            evidence=evidence,
            source_engine=f"rule:{rule.rule_id}@{rule.version}",
            observed_window=ctx.observed_window,
            provenance=Provenance(
                engine=ENGINE_NAME,
                engine_version=ENGINE_VERSION,
                source_unit=ctx.unit,
                input_hash=ctx.input_hash,
                produced_at=datetime.now(tz=UTC),
            ),
            triggered_by=tuple(sorted({t.identity_key for t in match.triggers})),
        )
