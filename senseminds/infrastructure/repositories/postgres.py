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
from collections.abc import Iterable

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from senseminds.domain.entities import Asset
from senseminds.findings import Finding
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
        # One row per condition: the newest observation of each identity_key.
        rows = self._s.execute(
            text(
                "SELECT DISTINCT ON (identity_key) document FROM application.finding "
                "WHERE unit = :unit "
                "ORDER BY identity_key, produced_at DESC, finding_id DESC"
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
                "artifact_ids = CAST(:aid AS JSONB) WHERE run_id = :rid"
            ),
            {"st": run.status.value, "fat": run.finished_at, "fc": run.finding_count,
             "ev": json.dumps(run.engine_versions, sort_keys=True),
             "aid": json.dumps(list(run.artifact_ids)), "rid": run.run_id},
        )

    def find(self, unit: str, input_hash: str) -> EngineRun | None:
        row = self._s.execute(
            text("SELECT run_id, unit, input_hash, status, started_at, finished_at, "
                 "finding_count, engine_versions, artifact_ids FROM application.engine_run "
                 "WHERE unit = :unit AND input_hash = :ih"),
            {"unit": unit, "ih": input_hash},
        ).one_or_none()
        return _engine_run(row) if row else None

    def for_unit(self, unit: str) -> list[EngineRun]:
        rows = self._s.execute(
            text("SELECT run_id, unit, input_hash, status, started_at, finished_at, "
                 "finding_count, engine_versions, artifact_ids FROM application.engine_run "
                 "WHERE unit = :unit ORDER BY started_at, run_id"),
            {"unit": unit},
        )
        return [_engine_run(r) for r in rows]

    def count(self) -> int:
        result = self._s.execute(text("SELECT count(*) FROM application.engine_run"))
        return int(result.scalar_one())


def _engine_run(row: object) -> EngineRun:
    return EngineRun(
        run_id=row[0], unit=row[1], input_hash=row[2], status=RunStatus(row[3]),
        started_at=row[4], finished_at=row[5], finding_count=row[6],
        engine_versions=_as_dict(row[7]) if row[7] else {},
        artifact_ids=tuple(json.loads(row[8]) if isinstance(row[8], str) else row[8]),
    )


def _as_dict_or_scalar(value: object) -> object:
    """A model-registry artifact round-trips as whatever JSON it was (dict/list/scalar)."""
    if isinstance(value, str):
        return json.loads(value)
    return value
