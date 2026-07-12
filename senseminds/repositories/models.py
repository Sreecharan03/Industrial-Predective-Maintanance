"""Application-aggregate domain models (ADR-019 D4).

Immutable models for aggregates that have no home in the analytics domain:
Reports and identity (User/Role). Like every other domain object they are frozen
value objects; repositories only map them to/from persistence, never mutate them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from senseminds.domain.base import FrozenModel


class ReportType(StrEnum):
    DAILY_ASSET_HEALTH = "daily_asset_health"
    MAINTENANCE_SUMMARY = "maintenance_summary"
    FORECAST_SUMMARY = "forecast_summary"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    EXECUTIVE_SUMMARY = "executive_summary"
    ENGINEERING_INVESTIGATION = "engineering_investigation"


class Persona(StrEnum):
    OPERATOR = "operator"
    MAINTENANCE_ENGINEER = "maintenance_engineer"
    RELIABILITY_ENGINEER = "reliability_engineer"
    PLANT_MANAGER = "plant_manager"
    EXECUTIVE = "executive"


class ReportStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


class Report(FrozenModel):
    """A generated engineering report - immutable once produced.

    ``cited_finding_ids`` + ``payload`` capture the grounded evidence the report
    was built from, so a stored report is reproducible: rebuilding from the same
    findings yields the same payload (ADR-018 §8).
    """

    report_id: str = Field(min_length=1)
    report_type: ReportType
    persona: Persona
    unit: str = Field(min_length=1)
    window_start: datetime | None = None
    window_end: datetime | None = None
    status: ReportStatus = ReportStatus.COMPLETE
    requested_by: str | None = None
    requested_at: datetime
    artifact_id: str | None = None
    cited_finding_ids: tuple[str, ...] = Field(default_factory=tuple)
    payload: dict[str, object] = Field(default_factory=dict)


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EngineRun(FrozenModel):
    """Audit record for one AnalysisUseCase execution (ADR-019 D5, R2).

    Keyed for idempotency by ``(unit, input_hash)``: one input can record only one
    run. Links the run to the artifacts it produced and the engine versions used.
    """

    run_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    input_hash: str = Field(min_length=1)
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    finding_count: int = 0
    engine_versions: dict[str, str] = Field(default_factory=dict)
    artifact_ids: tuple[str, ...] = Field(default_factory=tuple)


class Role(FrozenModel):
    """A role in the access model (operator, reliability_engineer, admin, ...)."""

    name: str = Field(min_length=1)
    description: str = ""


class User(FrozenModel):
    """A platform user and the roles they hold (the identity aggregate, R1)."""

    username: str = Field(min_length=1)
    email: str = ""
    hashed_password: str = ""
    is_active: bool = True
    roles: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime
