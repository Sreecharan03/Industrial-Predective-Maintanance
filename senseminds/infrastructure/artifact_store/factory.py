"""Select the artifact-store implementation from configuration.

The composition root calls this instead of naming a concrete store, so the
storage backend is a config choice (``SENSEMINDS_ARTIFACT_BACKEND``) rather than
a code change. Business logic depends only on the ``ArtifactStore`` port.
"""

from __future__ import annotations

from senseminds.config import Settings
from senseminds.infrastructure.artifact_store.base import ArtifactStore
from senseminds.infrastructure.artifact_store.local import LocalDiskArtifactStore


def build_artifact_store(settings: Settings) -> ArtifactStore:
    backend = settings.artifact_backend
    if backend == "local_disk":
        return LocalDiskArtifactStore(settings.artifact_root)
    if backend == "gcs":
        # Reserved: a GcsArtifactStore drops in here with no caller change.
        raise NotImplementedError(
            "artifact_backend='gcs' is reserved for a future GcsArtifactStore; "
            "use 'local_disk' (VM persistent disk) for the v1 deployment."
        )
    raise ValueError(f"unknown artifact_backend {backend!r}")
