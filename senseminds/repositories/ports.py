"""Aggregate-root repository ports (ADR-019 D4, R1).

One repository per **business aggregate**, not per table. Each owns a whole
aggregate and speaks only in immutable domain objects; implementations live in
`infrastructure` and only map domain <-> rows. Application services depend on
these interfaces, never on a concrete store.

`ModelRegistry` and `FeedbackRepository` are not redefined here - their ports
already live in `pattern_learning`; D4 adds Postgres implementations of them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from senseminds.domain.entities import Asset
from senseminds.findings import Finding
from senseminds.repositories.models import Report, Role, User
from senseminds.rules.models import RuleDefinition


class AssetRepository(ABC):
    """Owns the asset aggregate (asset + subsystems + sensors + thresholds)."""

    @abstractmethod
    def save(self, asset: Asset) -> None:
        """Upsert the asset aggregate (reference data, seeded from the catalog)."""

    @abstractmethod
    def get(self, unit: str) -> Asset | None: ...

    @abstractmethod
    def list_units(self) -> list[str]: ...


class FindingRepository(ABC):
    """Owns the finding aggregate (finding + evidence). **Append-only.**

    A finding is never updated. Re-adding an identical `finding_id` is a no-op;
    a new observation (different `input_hash` -> different `finding_id`) is a new
    row, linked to its predecessors through `identity_key` / `supersedes`.
    """

    @abstractmethod
    def add(self, finding: Finding) -> None: ...

    @abstractmethod
    def add_many(self, findings: object) -> int:
        """Append several findings; returns how many were submitted."""

    @abstractmethod
    def get(self, finding_id: str) -> Finding | None: ...

    @abstractmethod
    def for_unit(self, unit: str) -> list[Finding]:
        """All findings for a unit, oldest observation first."""

    @abstractmethod
    def history(self, identity_key: str) -> list[Finding]:
        """Every observation of one condition (identity), oldest first."""

    @abstractmethod
    def latest(self, identity_key: str) -> Finding | None:
        """The most recent observation of one condition."""

    @abstractmethod
    def count(self) -> int: ...


class ReportRepository(ABC):
    """Owns generated reports (immutable once produced)."""

    @abstractmethod
    def save(self, report: Report) -> None: ...

    @abstractmethod
    def get(self, report_id: str) -> Report | None: ...

    @abstractmethod
    def for_unit(self, unit: str) -> list[Report]: ...


class RuleVersionRepository(ABC):
    """Owns versioned rule definitions - an auditable, immutable version log."""

    @abstractmethod
    def save(self, rule: RuleDefinition) -> None:
        """Record a rule version; an existing (rule_id, version) is left intact."""

    @abstractmethod
    def get(self, rule_id: str, version: str) -> RuleDefinition | None: ...

    @abstractmethod
    def versions(self, rule_id: str) -> list[str]:
        """All recorded versions of a rule (audit trail), ascending."""

    @abstractmethod
    def list_rules(self) -> list[RuleDefinition]: ...


class UserRepository(ABC):
    """Owns the identity aggregate (users and the roles they hold)."""

    @abstractmethod
    def save(self, user: User) -> None: ...

    @abstractmethod
    def get(self, username: str) -> User | None: ...

    @abstractmethod
    def save_role(self, role: Role) -> None: ...

    @abstractmethod
    def get_role(self, name: str) -> Role | None: ...
