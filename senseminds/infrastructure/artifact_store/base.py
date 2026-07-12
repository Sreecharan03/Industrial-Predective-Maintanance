"""Artifact store port.

The interface (inner layers depend on this abstraction, ADR dependency rule)
for persisting and retrieving typed engine results. Implementations live
beside this file (local filesystem now; object storage / DB later) without any
inner layer needing to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from senseminds.domain.results import EngineResult


class ArtifactNotFoundError(KeyError):
    """Raised when a requested artifact id is absent from the store."""


class ArtifactStore(ABC):
    """Persist and retrieve typed engine results by id + type."""

    @abstractmethod
    def save(self, result: EngineResult) -> str:
        """Persist a result and return its artifact id."""

    @abstractmethod
    def load(self, artifact_id: str, result_type: type[EngineResult]) -> EngineResult:
        """Load and validate an artifact back into its typed result.

        Raises ArtifactNotFoundError if the id is unknown.
        """

    @abstractmethod
    def exists(self, artifact_id: str) -> bool:
        """Return whether an artifact id is present."""

    @abstractmethod
    def list_ids(self, result_type: type[EngineResult] | None = None) -> list[str]:
        """List artifact ids, optionally filtered to one result type."""
