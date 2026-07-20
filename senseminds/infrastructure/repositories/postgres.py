"""Postgres aggregate-root repositories (ADR-019 D4).

Each repository is a **pure mapper**: it (de)serialises an immutable domain
object to/from a row and holds no business logic. Every aggregate is stored as
indexed columns (for querying/audit) plus a ``document`` JSONB carrying the full
object, so reconstruction is byte-identical.

Repositories operate on a caller-supplied `Session` and never commit - the
`UnitOfWork` owns the transaction boundary, which is what makes multi-write
use-cases atomic and rollback-safe.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from senseminds.alerting.models import Alert, AlertKind, AlertStatus
from senseminds.domain.entities import Asset
from senseminds.findings import Finding
from senseminds.pattern_learning.feedback import (
    FeedbackRepository,
    FeedbackVerdict,
    HumanFeedback,
)
from senseminds.pattern_learning.registry import ModelMetadata, ModelRegistry
from senseminds.repositories.models import EngineRun, Report, Role, RunStatus, User
from senseminds.repositories.ports import (
    AssetRepository,
    FindingRepository,
    ReportRepository,
    RuleVersionRepository,
    UserRepository,
)
from senseminds.rules.models import RuleDefinition


def _doc(model: BaseModel) -> str:
    """Canonical JSON for a pydantic model's ``document`` column."""
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, default=str)


def _as_dict(value: object) -> dict:
    return json.loads(value) if isinstance(value, str) else dict(value)


class PostgresAssetRepository(AssetRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, asset: Asset) -> None:
        self._s.execute(
            text(
                "INSERT INTO application.asset (unit, equipment_class, display_name, document) "
                "VALUES (:unit, :ec, :dn, CAST(:doc AS JSONB)) "
                "ON CONFLICT (unit) DO UPDATE SET equipment_class = EXCLUDED.equipment_class, "
                "display_name = EXCLUDED.display_name, document = EXCLUDED.document, "
                "updated_at = now()"
            ),
            {"unit": asset.key, "ec": asset.equipment_class.value,
             "dn": asset.display_name, "doc": _doc(asset)},
        )

    def get(self, unit: str) -> Asset | None:
        row = self._s.execute(
            text("SELECT document FROM application.asset WHERE unit = :unit"), {"unit": unit}
        ).one_or_none()
        return Asset.model_validate(_as_dict(row[0])) if row else None

    def list_units(self) -> list[str]:
        rows = self._s.execute(text("SELECT unit FROM application.asset ORDER BY unit"))
        return [r[0] for r in rows]


class PostgresFindingRepository(FindingRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, finding: Finding) -> None:
        self._s.execute(
            text(
                "INSERT INTO application.finding (finding_id, identity_key, unit, finding_type, "
                "category, origin, severity, supersedes, observed_end, produced_at, document) "
                "VALUES (:fid, :idk, :unit, :ft, :cat, :org, :sev, :sup, :oend, :pat, "
                "CAST(:doc AS JSONB)) ON CONFLICT (finding_id) DO NOTHING"
            ),
            {
                "fid": finding.finding_id, "idk": finding.identity_key,
                "unit": finding.equipment_key, "ft": finding.finding_type.value,
                "cat": finding.category.value, "org": finding.origin.value,
                "sev": finding.severity.value, "sup": finding.supersedes,
                "oend": finding.observed_window.end, "pat": finding.provenance.produced_at,
                "doc": _doc(finding),
            },
        )

    def add_many(self, findings: Iterable[Finding]) -> int:
        n = 0
        for f in findings:
            self.add(f)
            n += 1
        return n

    def get(self, finding_id: str) -> Finding | None:
        row = self._s.execute(
            text("SELECT document FROM application.finding WHERE finding_id = :fid"),
            {"fid": finding_id},
        ).one_or_none()
        return Finding.model_validate(_as_dict(row[0])) if row else None

    def for_unit(self, unit: str) -> list[Finding]:
        rows = self._s.execute(
            text("SELECT document FROM application.finding WHERE unit = :unit "
                 "ORDER BY produced_at, finding_id"),
            {"unit": unit},
        )
        return [Finding.model_validate(_as_dict(r[0])) for r in rows]

    def current(self, unit: str) -> list[Finding]:
        """The newest observation of each condition the LATEST run still observed.

        Unchanged findings are not re-appended (see application/finding_delta.py),
        so "latest per identity" alone would keep a cleared condition alive forever.
        Filtering to the latest run's observed set makes a resolved condition
        disappear, while an unchanged one keeps its last observation.
        """
        rows = self._s.execute(
            text(
                """
                WITH latest AS (
                    SELECT observed_identities AS ids
                    FROM application.engine_run
                    WHERE unit = :unit AND status = 'completed'
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                SELECT DISTINCT ON (f.identity_key) f.document
                FROM application.finding f
                LEFT JOIN latest ON TRUE
                WHERE f.unit = :unit
                  AND (
                        latest.ids IS NULL
                     OR jsonb_array_length(latest.ids) = 0
                     OR jsonb_exists(latest.ids, f.identity_key)
                  )
                ORDER BY f.identity_key, f.produced_at DESC, f.finding_id DESC
                """
            ),
            {"unit": unit},
        )
        return [Finding.model_validate(_as_dict(r[0])) for r in rows]

    def history(self, identity_key: str) -> list[Finding]:
        rows = self._s.execute(
            text("SELECT document FROM application.finding WHERE identity_key = :idk "
                 "ORDER BY produced_at, finding_id"),
            {"idk": identity_key},
        )
        return [Finding.model_validate(_as_dict(r[0])) for r in rows]

    def latest(self, identity_key: str) -> Finding | None:
        row = self._s.execute(
            text("SELECT document FROM application.finding WHERE identity_key = :idk "
                 "ORDER BY produced_at DESC, finding_id DESC LIMIT 1"),
            {"idk": identity_key},
        ).one_or_none()
        return Finding.model_validate(_as_dict(row[0])) if row else None

    def count(self) -> int:
        return int(self._s.execute(text("SELECT count(*) FROM application.finding")).scalar_one())


class PostgresReportRepository(ReportRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, report: Report) -> None:
        self._s.execute(
            text(
                "INSERT INTO application.report (report_id, report_type, persona, unit, status, "
                "requested_at, document) VALUES (:rid, :rt, :pers, :unit, :st, :rat, "
                "CAST(:doc AS JSONB)) ON CONFLICT (report_id) DO UPDATE "
                "SET status = EXCLUDED.status, document = EXCLUDED.document"
            ),
            {"rid": report.report_id, "rt": report.report_type.value, "pers": report.persona.value,
             "unit": report.unit, "st": report.status.value, "rat": report.requested_at,
             "doc": _doc(report)},
        )

    def get(self, report_id: str) -> Report | None:
        row = self._s.execute(
            text("SELECT document FROM application.report WHERE report_id = :rid"),
            {"rid": report_id},
        ).one_or_none()
        return Report.model_validate(_as_dict(row[0])) if row else None

    def for_unit(self, unit: str) -> list[Report]:
        rows = self._s.execute(
            text("SELECT document FROM application.report WHERE unit = :unit "
                 "ORDER BY requested_at, report_id"),
            {"unit": unit},
        )
        return [Report.model_validate(_as_dict(r[0])) for r in rows]


class PostgresRuleVersionRepository(RuleVersionRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, rule: RuleDefinition) -> None:
        # a recorded version is immutable: keep the original on conflict (audit).
        self._s.execute(
            text(
                "INSERT INTO application.rule_version (rule_id, version, enabled, document) "
                "VALUES (:rid, :ver, :en, CAST(:doc AS JSONB)) "
                "ON CONFLICT (rule_id, version) DO NOTHING"
            ),
            {"rid": rule.rule_id, "ver": rule.version, "en": rule.enabled, "doc": _doc(rule)},
        )

    def get(self, rule_id: str, version: str) -> RuleDefinition | None:
        row = self._s.execute(
            text("SELECT document FROM application.rule_version "
                 "WHERE rule_id = :rid AND version = :ver"),
            {"rid": rule_id, "ver": version},
        ).one_or_none()
        return RuleDefinition.model_validate(_as_dict(row[0])) if row else None

    def versions(self, rule_id: str) -> list[str]:
        return [r[0] for r in self._s.execute(
            text("SELECT version FROM application.rule_version WHERE rule_id = :rid "
                 "ORDER BY version"), {"rid": rule_id})]

    def list_rules(self) -> list[RuleDefinition]:
        rows = self._s.execute(
            text("SELECT document FROM application.rule_version ORDER BY rule_id, version")
        )
        return [RuleDefinition.model_validate(_as_dict(r[0])) for r in rows]


class PostgresModelRegistry(ModelRegistry):
    """Auditable model-version registry. Artifacts must be JSON-serialisable
    (heavy binaries belong in the artifact store, referenced by id)."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, metadata: ModelMetadata, artifact: object) -> str:
        try:
            artifact_json = json.dumps(artifact, default=str)
        except TypeError as exc:  # pragma: no cover - defensive
            raise ValueError(
                "PostgresModelRegistry artifacts must be JSON-serialisable; "
                "store binaries in the artifact store and reference by id"
            ) from exc
        self._s.execute(
            text(
                "INSERT INTO application.model_registry (model_id, version, trained_at, "
                "feature_schema_version, seed, metadata, artifact) VALUES (:mid, :ver, :tat, "
                ":fsv, :seed, CAST(:meta AS JSONB), CAST(:art AS JSONB)) "
                "ON CONFLICT (model_id, version) DO NOTHING"
            ),
            {"mid": metadata.model_id, "ver": metadata.version, "tat": metadata.trained_at,
             "fsv": metadata.feature_schema_version, "seed": metadata.seed,
             "meta": _doc(metadata), "art": artifact_json},
        )
        return f"{metadata.model_id}@{metadata.version}"

    def get(self, model_id: str) -> tuple[ModelMetadata, object] | None:
        mid, _, ver = model_id.rpartition("@")
        row = self._s.execute(
            text("SELECT metadata, artifact FROM application.model_registry "
                 "WHERE model_id = :mid AND version = :ver"),
            {"mid": mid, "ver": ver},
        ).one_or_none()
        if row is None:
            return None
        return ModelMetadata.model_validate(_as_dict(row[0])), _as_dict_or_scalar(row[1])

    def list_ids(self) -> list[str]:
        return [f"{r[0]}@{r[1]}" for r in self._s.execute(
            text("SELECT model_id, version FROM application.model_registry "
                 "ORDER BY model_id, version"))]


class PostgresUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, user: User) -> None:
        self._s.execute(
            text(
                "INSERT INTO application.app_user (username, email, hashed_password, is_active, "
                "roles, document, created_at) VALUES (:u, :e, :hp, :act, CAST(:roles AS JSONB), "
                "CAST(:doc AS JSONB), :cat) ON CONFLICT (username) DO UPDATE SET email = "
                "EXCLUDED.email, hashed_password = EXCLUDED.hashed_password, "
                "is_active = EXCLUDED.is_active, roles = EXCLUDED.roles, "
                "document = EXCLUDED.document"
            ),
            {"u": user.username, "e": user.email, "hp": user.hashed_password,
             "act": user.is_active, "roles": json.dumps(list(user.roles)),
             "doc": _doc(user), "cat": user.created_at},
        )

    def get(self, username: str) -> User | None:
        row = self._s.execute(
            text("SELECT document FROM application.app_user WHERE username = :u"), {"u": username}
        ).one_or_none()
        return User.model_validate(_as_dict(row[0])) if row else None

    def save_role(self, role: Role) -> None:
        self._s.execute(
            text("INSERT INTO application.role (name, description) VALUES (:n, :d) "
                 "ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description"),
            {"n": role.name, "d": role.description},
        )

    def get_role(self, name: str) -> Role | None:
        row = self._s.execute(
            text("SELECT name, description FROM application.role WHERE name = :n"), {"n": name}
        ).one_or_none()
        return Role(name=row[0], description=row[1]) if row else None


class PostgresEngineRunRepository:
    """The analysis-run audit log (ADR-019 D5). Not append-only: a run row moves
    running -> completed/failed within the same transaction that persists its
    outputs."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def begin(self, run: EngineRun) -> bool:
        """Claim a run for (unit, input_hash). Returns True if this caller owns it,
        False if a run already exists (idempotent skip). Concurrency-safe: the
        UNIQUE(unit, input_hash) index serialises competing claimants."""
        result = self._s.execute(
            text(
                "INSERT INTO application.engine_run (run_id, unit, input_hash, status, started_at) "
                "VALUES (:rid, :unit, :ih, :st, :sat) "
                "ON CONFLICT (unit, input_hash) DO NOTHING RETURNING run_id"
            ),
            {"rid": run.run_id, "unit": run.unit, "ih": run.input_hash,
             "st": run.status.value, "sat": run.started_at},
        )
        return result.first() is not None

    def complete(self, run: EngineRun) -> None:
        self._s.execute(
            text(
                "UPDATE application.engine_run SET status = :st, finished_at = :fat, "
                "finding_count = :fc, engine_versions = CAST(:ev AS JSONB), "
                "artifact_ids = CAST(:aid AS JSONB), "
                "observed_identities = CAST(:obs AS JSONB) WHERE run_id = :rid"
            ),
            {"st": run.status.value, "fat": run.finished_at, "fc": run.finding_count,
             "ev": json.dumps(run.engine_versions, sort_keys=True),
             "aid": json.dumps(list(run.artifact_ids)),
             "obs": json.dumps(list(run.observed_identities)), "rid": run.run_id},
        )

    def find(self, unit: str, input_hash: str) -> EngineRun | None:
        row = self._s.execute(
            text("SELECT run_id, unit, input_hash, status, started_at, finished_at, "
                 "finding_count, engine_versions, artifact_ids, observed_identities "
                 "FROM application.engine_run WHERE unit = :unit AND input_hash = :ih"),
            {"unit": unit, "ih": input_hash},
        ).one_or_none()
        return _engine_run(row) if row else None

    def for_unit(self, unit: str) -> list[EngineRun]:
        rows = self._s.execute(
            text("SELECT run_id, unit, input_hash, status, started_at, finished_at, "
                 "finding_count, engine_versions, artifact_ids, observed_identities "
                 "FROM application.engine_run WHERE unit = :unit ORDER BY started_at, run_id"),
            {"unit": unit},
        )
        return [_engine_run(r) for r in rows]

    def last_learned_at(self, unit: str) -> datetime | None:
        """When the Phase-B models last ran for this asset (throttling)."""
        row = self._s.execute(
            text("SELECT max(started_at) FROM application.engine_run "
                 "WHERE unit = :unit AND learned AND status = 'completed'"),
            {"unit": unit},
        ).one_or_none()
        return row[0] if row and row[0] else None

    def count(self) -> int:
        result = self._s.execute(text("SELECT count(*) FROM application.engine_run"))
        return int(result.scalar_one())


def _engine_run(row: object) -> EngineRun:
    return EngineRun(
        run_id=row[0], unit=row[1], input_hash=row[2], status=RunStatus(row[3]),
        started_at=row[4], finished_at=row[5], finding_count=row[6],
        engine_versions=_as_dict(row[7]) if row[7] else {},
        artifact_ids=tuple(json.loads(row[8]) if isinstance(row[8], str) else row[8]),
        observed_identities=tuple(
            json.loads(row[9]) if isinstance(row[9], str) else (row[9] or [])
        ) if len(row) > 9 else (),
    )


def _as_dict_or_scalar(value: object) -> object:
    """A model-registry artifact round-trips as whatever JSON it was (dict/list/scalar)."""
    if isinstance(value, str):
        return json.loads(value)
    return value


class PostgresAlertRepository:
    """The escalation outbox. Unlike findings, alert rows ARE mutated - but only
    their delivery bookkeeping (status/attempts/error/sent_at); what happened and
    why (kind, payload) is immutable once written."""

    _COLUMNS = ("alert_id, unit, identity_key, finding_id, kind, severity, subject, "
                "payload, status, attempts, last_error, created_at, sent_at")

    def __init__(self, session: Session) -> None:
        self._s = session

    def add_many(self, alerts: Iterable[Alert]) -> int:
        n = 0
        for a in alerts:
            self._s.execute(
                text(
                    "INSERT INTO application.alert (alert_id, unit, identity_key, "
                    "finding_id, kind, severity, subject, payload, status, attempts, "
                    "created_at) VALUES (:aid, :unit, :idk, :fid, :kind, :sev, :subj, "
                    "CAST(:payload AS JSONB), :status, :att, :cat) "
                    "ON CONFLICT (alert_id) DO NOTHING"
                ),
                {"aid": a.alert_id, "unit": a.unit, "idk": a.identity_key,
                 "fid": a.finding_id, "kind": a.kind.value, "sev": a.severity,
                 "subj": a.subject, "payload": json.dumps(a.payload, default=str),
                 "status": a.status.value, "att": a.attempts, "cat": a.created_at},
            )
            n += 1
        return n

    def latest_by_identity(self, unit: str) -> dict[str, Alert]:
        """Newest alert per condition - the policy's view of each open incident."""
        rows = self._s.execute(
            text(
                f"SELECT DISTINCT ON (identity_key) {self._COLUMNS} "
                "FROM application.alert WHERE unit = :unit "
                "ORDER BY identity_key, created_at DESC"
            ),
            {"unit": unit},
        )
        alerts = [_alert(r) for r in rows]
        return {a.identity_key: a for a in alerts}

    def pending(self, max_attempts: int) -> list[Alert]:
        rows = self._s.execute(
            text(
                f"SELECT {self._COLUMNS} FROM application.alert "
                "WHERE status = 'pending' AND attempts < :max ORDER BY created_at"
            ),
            {"max": max_attempts},
        )
        return [_alert(r) for r in rows]

    def mark(
        self,
        alert_id: str,
        status: AlertStatus,
        attempts: int,
        last_error: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        self._s.execute(
            text(
                "UPDATE application.alert SET status = :status, attempts = :att, "
                "last_error = :err, sent_at = COALESCE(:sat, sent_at) "
                "WHERE alert_id = :aid"
            ),
            {"status": status.value, "att": attempts, "err": last_error,
             "sat": sent_at, "aid": alert_id},
        )

    def recent(self, limit: int = 100, unit: str | None = None) -> list[Alert]:
        clause = "WHERE unit = :unit" if unit else ""
        rows = self._s.execute(
            text(f"SELECT {self._COLUMNS} FROM application.alert {clause} "
                 "ORDER BY created_at DESC LIMIT :lim"),
            {"lim": limit, **({"unit": unit} if unit else {})},
        )
        return [_alert(r) for r in rows]

    def count(self) -> int:
        return int(self._s.execute(
            text("SELECT count(*) FROM application.alert")).scalar_one())


def _alert(row: object) -> Alert:
    return Alert(
        alert_id=row[0], unit=row[1], identity_key=row[2], finding_id=row[3],
        kind=AlertKind(row[4]), severity=row[5], subject=row[6],
        payload=_as_dict(row[7]) if row[7] else {}, status=AlertStatus(row[8]),
        attempts=row[9], last_error=row[10], created_at=row[11], sent_at=row[12],
    )


class PostgresFeedbackRepository(FeedbackRepository):
    """The label store (ADR-016 R2). Append-only; a changed verdict is a new row.

    Re-submitting the SAME verdict by the SAME author on the same condition is an
    idempotent no-op - a double-clicked thumbs-up must not fabricate a second
    label - while an actual change of mind is recorded as a new row so the label
    history stays auditable.
    """

    _COLUMNS = ("feedback_id, identity_key, finding_id, unit, verdict, author, "
                "note, created_at")

    def __init__(self, session: Session) -> None:
        self._s = session

    def record(self, feedback: HumanFeedback) -> None:
        latest = self.latest_for(feedback.finding_identity_key, feedback.author)
        if latest is not None and latest.verdict is feedback.verdict:
            return  # same verdict, same author -> nothing changed
        self._s.execute(
            text(
                "INSERT INTO application.feedback (feedback_id, identity_key, "
                "finding_id, unit, verdict, author, note, created_at) "
                "VALUES (:fid, :idk, :find, :unit, :verdict, :author, :note, :cat) "
                "ON CONFLICT (feedback_id) DO NOTHING"
            ),
            {"fid": feedback.feedback_id or uuid.uuid4().hex,
             "idk": feedback.finding_identity_key, "find": feedback.finding_id,
             "unit": feedback.unit, "verdict": feedback.verdict.value,
             "author": feedback.author, "note": feedback.note,
             "cat": feedback.created_at},
        )

    def for_finding(self, identity_key: str) -> list[HumanFeedback]:
        rows = self._s.execute(
            text(f"SELECT {self._COLUMNS} FROM application.feedback "
                 "WHERE identity_key = :idk ORDER BY created_at"),
            {"idk": identity_key},
        )
        return [_feedback(r) for r in rows]

    def all(self) -> list[HumanFeedback]:
        rows = self._s.execute(
            text(f"SELECT {self._COLUMNS} FROM application.feedback ORDER BY created_at")
        )
        return [_feedback(r) for r in rows]

    def latest_for(self, identity_key: str, author: str) -> HumanFeedback | None:
        row = self._s.execute(
            text(f"SELECT {self._COLUMNS} FROM application.feedback "
                 "WHERE identity_key = :idk AND author = :a "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"idk": identity_key, "a": author},
        ).one_or_none()
        return _feedback(row) if row else None

    def latest_by_identity(self, unit: str | None = None) -> dict[str, HumanFeedback]:
        """The current verdict per condition - the newest row wins, whoever wrote it."""
        clause = "WHERE unit = :unit" if unit else ""
        rows = self._s.execute(
            text(f"SELECT DISTINCT ON (identity_key) {self._COLUMNS} "
                 f"FROM application.feedback {clause} "
                 "ORDER BY identity_key, created_at DESC"),
            {"unit": unit} if unit else {},
        )
        return {f.finding_identity_key: f for f in (_feedback(r) for r in rows)}

    def recent(self, limit: int = 100, unit: str | None = None) -> list[HumanFeedback]:
        clause = "WHERE unit = :unit" if unit else ""
        rows = self._s.execute(
            text(f"SELECT {self._COLUMNS} FROM application.feedback {clause} "
                 "ORDER BY created_at DESC LIMIT :lim"),
            {"lim": limit, **({"unit": unit} if unit else {})},
        )
        return [_feedback(r) for r in rows]

    def stats(self) -> dict[str, object]:
        """Label readiness for Phase C: verdict mix + how many DISTINCT conditions
        carry a current label (re-labelling the same condition does not move this)."""
        by_verdict = {
            row[0]: int(row[1])
            for row in self._s.execute(
                text("SELECT verdict, count(*) FROM ("
                     "  SELECT DISTINCT ON (identity_key) identity_key, verdict "
                     "  FROM application.feedback ORDER BY identity_key, created_at DESC"
                     ") latest GROUP BY verdict")
            )
        }
        totals = self._s.execute(
            text("SELECT count(*), count(DISTINCT identity_key), "
                 "count(DISTINCT author), count(DISTINCT unit) FROM application.feedback")
        ).one()
        return {
            "labelled_conditions": int(totals[1]),
            "total_verdicts": int(totals[0]),
            "contributors": int(totals[2]),
            "units_covered": int(totals[3]),
            "by_verdict": by_verdict,
        }

    def count(self) -> int:
        return int(self._s.execute(
            text("SELECT count(*) FROM application.feedback")).scalar_one())


def _feedback(row: object) -> HumanFeedback:
    return HumanFeedback(
        feedback_id=row[0], finding_identity_key=row[1], finding_id=row[2],
        unit=row[3], verdict=FeedbackVerdict(row[4]), author=row[5],
        note=row[6] or "", created_at=row[7],
    )
