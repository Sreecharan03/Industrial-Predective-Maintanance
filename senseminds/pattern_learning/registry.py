"""Model registry (ADR-016 §7).

Versioned model metadata + artifacts so every learned output is reproducible and
traceable to `(model_id, version, seed, feature_schema, training window)`. The
embedded implementation holds artifacts in memory; a persistent backend can
implement the same interface later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import Field

from senseminds.domain.base import FrozenModel


class ModelMetadata(FrozenModel):
    """Everything needed to reproduce and trust a model run."""

    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    trained_at: datetime
    training_window_start: datetime | None = None
    training_window_end: datetime | None = None
    feature_schema_version: str
    seed: int
    hyperparameters: dict[str, object] = Field(default_factory=dict)


class ModelRegistry(ABC):
    """Persist and retrieve versioned model artifacts + metadata."""

    @abstractmethod
    def save(self, metadata: ModelMetadata, artifact: object) -> str: ...

    @abstractmethod
    def get(self, model_id: str) -> tuple[ModelMetadata, object] | None: ...

    @abstractmethod
    def list_ids(self) -> list[str]: ...


class InMemoryModelRegistry(ModelRegistry):
    """In-memory model registry."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[ModelMetadata, object]] = {}

    def save(self, metadata: ModelMetadata, artifact: object) -> str:
        key = f"{metadata.model_id}@{metadata.version}"
        self._store[key] = (metadata, artifact)
        return key

    def get(self, model_id: str) -> tuple[ModelMetadata, object] | None:
        return self._store.get(model_id)

    def list_ids(self) -> list[str]:
        return sorted(self._store)
