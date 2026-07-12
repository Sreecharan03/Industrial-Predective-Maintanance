"""Local filesystem artifact store.

Persists each typed engine result as a JSON document under
``<root>/<ResultType>/<artifact_id>.json``. Writes are atomic (temp file +
rename) so a crashed or concurrent write can never leave a half-written
artifact that a reader might load. Suitable for single-node/studio use;
swappable for object storage or a DB behind ``ArtifactStore`` later.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from senseminds.domain.results import EngineResult
from senseminds.infrastructure.artifact_store.base import (
    ArtifactNotFoundError,
    ArtifactStore,
)
from senseminds.infrastructure.logging import get_logger

_log = get_logger(__name__)


class LocalArtifactStore(ArtifactStore):
    """Filesystem-backed artifact store rooted at a directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _type_dir(self, result_type_name: str) -> Path:
        path = self._root / result_type_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, result_type_name: str, artifact_id: str) -> Path:
        # artifact_id is used as a filename; reject path separators so an id
        # can never escape its type directory.
        if "/" in artifact_id or "\\" in artifact_id or artifact_id in {"", ".", ".."}:
            raise ValueError(f"invalid artifact_id for filesystem store: {artifact_id!r}")
        return self._type_dir(result_type_name) / f"{artifact_id}.json"

    def save(self, result: EngineResult) -> str:
        path = self._path(result.result_type, result.artifact_id)
        payload = result.model_dump_json(indent=2)
        # Atomic write: temp file in the same dir, then rename.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        _log.info(
            "artifact_saved",
            extra={"artifact_id": result.artifact_id, "result_type": result.result_type},
        )
        return result.artifact_id

    def load(self, artifact_id: str, result_type: type[EngineResult]) -> EngineResult:
        path = self._path(result_type.__name__, artifact_id)
        if not path.exists():
            raise ArtifactNotFoundError(
                f"{result_type.__name__} artifact {artifact_id!r} not found under {self._root}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return result_type.model_validate(data)

    def exists(self, artifact_id: str) -> bool:
        return any(
            (self._root / type_dir.name / f"{artifact_id}.json").exists()
            for type_dir in self._root.iterdir()
            if type_dir.is_dir()
        )

    def list_ids(self, result_type: type[EngineResult] | None = None) -> list[str]:
        if result_type is not None:
            type_dir = self._root / result_type.__name__
            if not type_dir.exists():
                return []
            return sorted(p.stem for p in type_dir.glob("*.json"))
        ids: list[str] = []
        for type_dir in self._root.iterdir():
            if type_dir.is_dir():
                ids.extend(p.stem for p in type_dir.glob("*.json"))
        return sorted(ids)
