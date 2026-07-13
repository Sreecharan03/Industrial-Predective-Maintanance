"""Analysis worker (Platform Integration).

A long-running process that keeps the intelligence current as sensor history
accumulates. Each cycle runs the atomic AnalysisUseCase for every unit; because
runs are idempotent by (unit, input_hash), a cycle with no new data is a cheap
no-op, and a cycle after fresh readings produces a new run. Live-stream ingestion
(OPC-UA/MQTT) is a future TimeSeriesSource behind the same seam; today the worker
reads accumulated history from TimescaleDB.

Orchestration only - it composes frozen components and never reaches inside them.
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Sequence

from senseminds.application.analysis_use_case import AnalysisRunResult, AnalysisUseCase
from senseminds.config import Settings, get_settings
from senseminds.infrastructure.artifact_store.local import LocalArtifactStore
from senseminds.infrastructure.db import build_database
from senseminds.infrastructure.logging import configure_logging, get_logger
from senseminds.ingestion import DbTimeSeriesSource, TimeSeriesSource

_log = get_logger(__name__)


class AnalysisWorker:
    """Runs the analysis pipeline for every unit, on an interval."""

    def __init__(
        self,
        use_case: AnalysisUseCase,
        source: TimeSeriesSource,
        interval_seconds: int = 300,
        units: Sequence[str] | None = None,
    ) -> None:
        self._use_case = use_case
        self._source = source
        self._interval = interval_seconds
        self._units = list(units) if units is not None else None
        self._stop = threading.Event()

    def _targets(self) -> list[str]:
        return self._units if self._units is not None else self._source.available_units()

    def run_once(self) -> list[AnalysisRunResult]:
        """One cycle over all units. Returns each unit's run result."""
        results: list[AnalysisRunResult] = []
        for unit in self._targets():
            try:
                result = self._use_case.run(unit)
                results.append(result)
                _log.info("analysis_cycle_unit", extra={
                    "unit": unit, "findings": result.finding_count, "replayed": result.replayed})
            except Exception:  # one unit's failure must not stop the cycle
                _log.exception("analysis_cycle_unit_failed", extra={"unit": unit})
        return results

    def run_forever(self) -> None:  # pragma: no cover - loop
        signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        _log.info("worker_started", extra={"interval_seconds": self._interval})
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self._interval)
        _log.info("worker_stopped")


def main(settings: Settings | None = None) -> None:  # pragma: no cover - entrypoint
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = build_database(settings)
    if settings.bootstrap_on_start:
        _maybe_bootstrap(db, settings)
    source = DbTimeSeriesSource(db)
    use_case = AnalysisUseCase(
        db, LocalArtifactStore(settings.artifact_root), source,
        learning_enabled=settings.learning_enabled,
        learning_interval_minutes=settings.learning_interval_minutes,
    )
    AnalysisWorker(use_case, source, settings.worker_interval_seconds).run_forever()


def _maybe_bootstrap(db, settings: Settings) -> None:  # noqa: ANN001  # pragma: no cover
    from senseminds.application.bootstrap import bootstrap_units

    if not DbTimeSeriesSource(db).available_units():
        processed = settings.legacy_reports_root / "processed"
        if processed.exists():
            _log.info("worker_bootstrap", extra={"processed": str(processed)})
            bootstrap_units(db, processed)


if __name__ == "__main__":  # pragma: no cover
    main()
