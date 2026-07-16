"""Application settings.

All configuration is loaded from environment variables (12-factor), validated
by Pydantic at startup so a misconfigured deployment fails fast and loudly
rather than midway through a run. `get_settings()` is cached so the environment
is read and validated exactly once per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated platform configuration (env-prefixed ``SENSEMINDS_``)."""

    model_config = SettingsConfigDict(
        env_prefix="SENSEMINDS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: str = Field(
        default="local",
        description="Deployment environment name (local, dev, staging, prod).",
    )
    log_level: str = Field(default="INFO", description="Root log level.")

    # Where engine artifacts (typed results + provenance) are persisted.
    artifact_root: Path = Field(
        default=Path("./artifacts"),
        description="Root directory for the local artifact store.",
    )

    # Read-only pointer to the already-produced Phase-1/2 analysis, which the
    # ingestion/quality refactor (M1) will parity-test against.
    legacy_reports_root: Path = Field(
        default=Path("../Datasets"),
        description="Root of the existing Datasets/ analysis (processed, reports, figures).",
    )

    # Persistence (ADR-019). One Postgres+TimescaleDB instance today; the three
    # logical stores (sensor_history / knowledge / application) each resolve their
    # own URL so a future physical split is a config change, not a code change
    # (ADR-019 R4). Unset per-store URLs fall back to ``database_url``.
    database_url: str = Field(
        default="postgresql+psycopg://senseminds:senseminds@localhost:5432/senseminds",
        description="Base SQLAlchemy URL for the Postgres+TimescaleDB instance.",
    )
    sensor_history_url: str | None = Field(
        default=None, description="Override URL for the sensor_history store (else database_url)."
    )
    knowledge_url: str | None = Field(
        default=None, description="Override URL for the knowledge store (else database_url)."
    )
    application_url: str | None = Field(
        default=None, description="Override URL for the application store (else database_url)."
    )

    # LLM communication layer (ADR-018). With no key the deterministic stub is
    # used, so the platform runs fully offline; set the key to enable Groq.
    groq_api_key: str = Field(
        default="", description="Groq API key; empty => deterministic stub (offline)."
    )
    llm_model: str = Field(
        default="llama-3.3-70b-versatile", description="Groq-hosted model id."
    )

    # API auth (ADR-018 serving). Override the secret in every real deployment.
    jwt_secret: str = Field(
        default="dev-insecure-change-me", description="HS256 signing secret for API tokens."
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    access_token_ttl_minutes: int = Field(default=720, description="Access-token lifetime.")
    default_admin_username: str = Field(default="admin", description="Seed admin username.")
    default_admin_password: str = Field(
        default="admin", description="Seed admin password (change in every real deployment)."
    )

    # Ingestion / analysis worker.
    worker_interval_seconds: int = Field(
        default=300, description="Seconds between analysis cycles over all units."
    )
    bootstrap_on_start: bool = Field(
        default=True, description="Load processed CSVs into sensor history if empty, on start."
    )

    # Alert escalation (email). Alerts are always RECORDED; email is sent only when
    # SMTP is configured. A mail failure never affects the analysis - the alert row
    # is committed with the finding (outbox pattern) and delivery is retried.
    smtp_host: str = Field(default="", description="SMTP server; empty disables email.")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_starttls: bool = Field(default=True)
    mail_from: str = Field(default="")
    mail_to: str = Field(default="", description="Comma-separated recipients.")
    alert_reminder_minutes: int = Field(
        default=30, description="Escalate again if still critical after this long."
    )
    alert_cooldown_minutes: int = Field(
        default=15, description="Suppress re-triggers of the same condition (flapping)."
    )
    dashboard_url: str = Field(
        default="http://localhost:3000", description="Used for the link in alert emails."
    )

    # Phase B (pattern learning + forecasting). These look for slow trends, so they
    # run on their own, slower cadence rather than on every 30-second analysis.
    learning_enabled: bool = Field(
        default=True, description="Run novelty / regime / forecast models."
    )
    learning_interval_minutes: int = Field(
        default=30, description="Minimum minutes between Phase-B runs per asset."
    )

    # Live machine simulator (testing / demo). Generates 30-second data.
    live_data_root: Path = Field(
        default=Path("./live_data"), description="Where the growing 30s CSVs are written."
    )
    sim_backfill_days: float = Field(
        default=3.0, description="History to back-fill so the engines have a baseline."
    )
    sim_reset: bool = Field(
        default=False,
        description="Wipe sensor history + findings before seeding (destroys persisted data).",
    )
    sim_drift_unit: str = Field(
        default="SC-126", description="Machine given a slow degradation (empty = none)."
    )
    sim_drift_column: str = Field(
        default="Discharge Pressure", description="Sensor that drifts toward its limit."
    )
    sim_drift_ramp_minutes: float = Field(
        default=20.0, description="Minutes for the drift to cross the operating limit."
    )

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}, got {value!r}")
        return upper

    @field_validator("environment")
    @classmethod
    def _valid_environment(cls, value: str) -> str:
        allowed = {"local", "dev", "staging", "prod"}
        lower = value.lower()
        if lower not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}, got {value!r}")
        return lower


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings (read from env once)."""
    return Settings()
