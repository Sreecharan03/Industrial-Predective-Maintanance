"""Application persistence (ADR-019 D4).

Aggregate-root repositories, append-only findings, multi-run accumulation with
identity intact, reproducible reports, auditable rule/model versions, and
transactional rollback. Integration test - skipped unless a Postgres/TimescaleDB
is reachable (``SENSEMINDS_DATABASE_URL``).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy
from senseminds.config import Settings
from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
    ObservedWindow,
)
from senseminds.pattern_learning.registry import ModelMetadata
from senseminds.repositories import Persona, Report, ReportType, Role, User
from senseminds.rules.catalog import DEFAULT_RULES

_T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _db_url() -> str:
    return os.environ.get("SENSEMINDS_DATABASE_URL") or Settings().database_url


def _db_available(url: str) -> bool:
    try:
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(not _db_available(_db_url()), reason="TimescaleDB not available")


def _finding(
    identity_key: str, finding_id: str, produced_at: datetime,
    unit: str = "SC-126", supersedes: str | None = None, severity: Severity = Severity.WARNING,
) -> Finding:
    return Finding(
        finding_id=finding_id, identity_key=identity_key,
        finding_type=FindingType.THRESHOLD_MISSPECIFIED, category=FindingCategory.THRESHOLD,
        scope=FindingScope.SENSOR, origin=FindingOrigin.DERIVED,
        summary="discharge pressure threshold mis-specified", detail="rationale",
        target_key="discharge_pressure", equipment_key=unit, subsystem_key="compression",
        severity=severity, confidence=Confidence(value=0.9, rationale="coverage"),
        evidence=(Evidence(artifact_id="art-1", description="pct outside", observed_value=94.8),),
        source_engine="threshold", observed_window=ObservedWindow(start=_T0, end=produced_at),
        provenance=Provenance(engine="threshold", engine_version="0.1.0", source_unit=unit,
                              input_hash=finding_id, produced_at=produced_at),
        supersedes=supersedes,
    )


@pytest.fixture(scope="module")
def db():  # noqa: ANN201
    from senseminds.infrastructure.db import build_database
    from senseminds.infrastructure.db.migrate import upgrade

    url = _db_url()
    upgrade(url)  # idempotent
    database = build_database(Settings(database_url=url))
    yield database
    database.dispose()


@pytest.fixture(autouse=True)
def _clean(db):  # noqa: ANN001, ANN202
    from senseminds.infrastructure.db import APPLICATION

    with db.session(APPLICATION) as session:
        session.execute(sqlalchemy.text(
            "TRUNCATE application.finding, application.report, application.rule_version, "
            "application.model_registry, application.asset, application.app_user, application.role"
        ))
    yield


def _uow(db):  # noqa: ANN001, ANN202
    from senseminds.infrastructure.repositories import UnitOfWork

    return UnitOfWork(db)


# ------------------------------ findings ------------------------------

def test_finding_round_trip_is_identical(db) -> None:  # noqa: ANN001
    f = _finding("id-a", "fid-1", _T0)
    with _uow(db) as uow:
        uow.findings.add(f)
    with _uow(db) as uow:
        assert uow.findings.get("fid-1") == f  # byte-identical reconstruction


def test_findings_are_append_only_in_db(db) -> None:  # noqa: ANN001
    from senseminds.infrastructure.db import APPLICATION

    with _uow(db) as uow:
        uow.findings.add(_finding("id-a", "fid-1", _T0))
    # the DB trigger must reject both UPDATE and DELETE
    for stmt in ("UPDATE application.finding SET severity = 'critical'",
                 "DELETE FROM application.finding"):
        with pytest.raises(Exception) as exc, db.session(APPLICATION) as session:
            session.execute(sqlalchemy.text(stmt))
        assert "append-only" in str(exc.value).lower()


def test_reinserting_same_finding_id_is_noop(db) -> None:  # noqa: ANN001
    f = _finding("id-a", "fid-1", _T0)
    with _uow(db) as uow:
        uow.findings.add(f)
        uow.findings.add(f)  # same id
    with _uow(db) as uow:
        assert uow.findings.count() == 1


def test_history_accumulates_with_identity_intact(db) -> None:  # noqa: ANN001
    # Two runs of the SAME condition (identity) over different windows -> two
    # observations (distinct finding_ids), linked by identity_key.
    run_a = _finding("id-shared", "fid-a", _T0)
    run_b = _finding("id-shared", "fid-b", _T0 + timedelta(days=30), supersedes="fid-a")
    with _uow(db) as uow:
        uow.findings.add(run_a)
    with _uow(db) as uow:  # a later, separate analysis run
        uow.findings.add(run_b)
    with _uow(db) as uow:
        history = uow.findings.history("id-shared")
        latest = uow.findings.latest("id-shared")
    assert [f.finding_id for f in history] == ["fid-a", "fid-b"]  # accumulated, oldest first
    assert latest.finding_id == "fid-b"  # newest observation
    assert latest.supersedes == "fid-a"  # supersession link preserved


def test_multi_asset_findings_are_isolated(db) -> None:  # noqa: ANN001
    with _uow(db) as uow:
        uow.findings.add(_finding("id-126", "f126", _T0, unit="SC-126"))
        uow.findings.add(_finding("id-114", "f114", _T0, unit="SC-114"))
    with _uow(db) as uow:
        assert [f.finding_id for f in uow.findings.for_unit("SC-126")] == ["f126"]
        assert [f.finding_id for f in uow.findings.for_unit("SC-114")] == ["f114"]
        assert uow.findings.count() == 2


# ------------------------------ reports ------------------------------

def _build_report(unit: str, findings: list[Finding]) -> Report:
    """Deterministic report from grounded findings (reproducible)."""
    return Report(
        report_id=f"{unit}:daily", report_type=ReportType.DAILY_ASSET_HEALTH,
        persona=Persona.RELIABILITY_ENGINEER, unit=unit, requested_at=_T0,
        cited_finding_ids=tuple(sorted(f.finding_id for f in findings)),
        payload={"finding_count": len(findings),
                 "severities": sorted(f.severity.value for f in findings)},
    )


def test_report_is_reproducible(db) -> None:  # noqa: ANN001
    findings = [_finding("id-a", "fid-1", _T0), _finding("id-b", "fid-2", _T0)]
    report = _build_report("SC-126", findings)
    with _uow(db) as uow:
        uow.reports.save(report)
    with _uow(db) as uow:
        stored = uow.reports.get("SC-126:daily")
    assert stored == report  # retrieval fidelity
    assert _build_report("SC-126", findings) == stored  # rebuild from same evidence == stored


# ------------------------- auditable versions -------------------------

def test_rule_versions_are_auditable(db) -> None:  # noqa: ANN001
    rule = DEFAULT_RULES[0]
    v2 = rule.model_copy(update={"version": "9.9.9"})
    with _uow(db) as uow:
        uow.rules.save(rule)
        uow.rules.save(v2)
        uow.rules.save(rule.model_copy(update={"enabled": not rule.enabled}))  # re-save v1: no-op
    with _uow(db) as uow:
        assert uow.rules.versions(rule.rule_id) == sorted([rule.version, "9.9.9"])
        assert uow.rules.get(rule.rule_id, rule.version) == rule  # v1 unchanged (immutable)


def test_model_versions_are_auditable(db) -> None:  # noqa: ANN001
    m1 = ModelMetadata(model_id="isolation_forest", version="0.1.0", trained_at=_T0,
                       feature_schema_version="1", seed=7, hyperparameters={"n": 100})
    m2 = m1.model_copy(update={"version": "0.2.0", "seed": 8})
    with _uow(db) as uow:
        uow.models.save(m1, {"threshold": 0.5})
        uow.models.save(m2, {"threshold": 0.6})
    with _uow(db) as uow:
        assert uow.models.list_ids() == ["isolation_forest@0.1.0", "isolation_forest@0.2.0"]
        meta, artifact = uow.models.get("isolation_forest@0.2.0")
        assert (meta.version, meta.seed) == ("0.2.0", 8)
        assert artifact == {"threshold": 0.6}


# ------------------------- transactions -------------------------

def test_unit_of_work_rolls_back_on_error(db) -> None:  # noqa: ANN001
    with pytest.raises(RuntimeError), _uow(db) as uow:
        uow.findings.add(_finding("id-a", "fid-1", _T0))
        uow.reports.save(_build_report("SC-126", []))
        raise RuntimeError("simulated failure mid-transaction")
    with _uow(db) as uow:
        assert uow.findings.count() == 0  # nothing persisted
        assert uow.reports.get("SC-126:daily") is None


def test_unit_of_work_commits_atomically(db) -> None:  # noqa: ANN001
    with _uow(db) as uow:
        uow.findings.add(_finding("id-a", "fid-1", _T0))
        uow.reports.save(_build_report("SC-126", []))
        uow.users.save_role(Role(name="reliability_engineer", description="RE"))
        uow.users.save(User(username="alice", roles=("reliability_engineer",), created_at=_T0))
    with _uow(db) as uow:
        assert uow.findings.count() == 1
        assert uow.reports.get("SC-126:daily") is not None
        assert uow.users.get("alice").roles == ("reliability_engineer",)
        assert uow.users.get_role("reliability_engineer").description == "RE"
