"""Live machine simulator (testing / demo).

Writes a growing 30-second CSV per machine — exactly like a plant historian or log
export — then tails it just after each tick, validates the new rows, persists them
to TimescaleDB and re-runs the analysis. The dashboard and Copilot update by
themselves.

Nothing here is special-cased: it feeds the SAME ingestion ports a real machine
would (`ReadingValidation` -> `ReadingSink`), and triggers the SAME AnalysisUseCase.
Swap this for an OPC-UA / MQTT adapter and the rest of the platform is unchanged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from senseminds.application.analysis_use_case import AnalysisUseCase
from senseminds.infrastructure.artifact_store.local import LocalArtifactStore
from senseminds.infrastructure.db import APPLICATION, KNOWLEDGE, SENSOR_HISTORY, Database
from senseminds.infrastructure.logging import get_logger
from senseminds.ingestion import (
    DbReadingSink,
    DbTimeSeriesSource,
    ProcessedCsvSource,
    ReadingValidation,
    UnitSensorCatalog,
    iter_readings,
)
from senseminds.ingestion.csv_source import _UNIT_FILE_MAP
from senseminds.simulation.generator import TICK, Drift, MachineGenerator, align_to_tick
from senseminds.simulation.profiles import profile_unit

_log = get_logger(__name__)


@dataclass
class SimulatorConfig:
    processed_dir: Path            # real data, used only to learn each sensor's profile
    live_dir: Path                 # where the growing 30s CSVs are written
    artifact_root: Path
    backfill_days: float = 3.0     # history so the engines have something to stand on
    drift: Drift | None = None
    reset: bool = True             # start the demo from a clean slate


class LiveSimulator:
    def __init__(self, db: Database, cfg: SimulatorConfig) -> None:
        self._db = db
        self._cfg = cfg
        self._sink = DbReadingSink(db)
        self._sensors = UnitSensorCatalog(db)
        self._analysis = AnalysisUseCase(
            db, LocalArtifactStore(cfg.artifact_root), DbTimeSeriesSource(db)
        )
        self._generators: dict[str, MachineGenerator] = {}
        self._live_start = align_to_tick(datetime.now(tz=UTC).replace(tzinfo=None))

    # ------------------------------- seeding -------------------------------

    def _wipe(self) -> None:
        with self._db.session(SENSOR_HISTORY) as s:
            s.execute(text("TRUNCATE sensor_history.sensor_reading, "
                           "sensor_history.ingest_watermark, sensor_history.unit_sensor"))
        with self._db.session(APPLICATION) as s:
            s.execute(text("TRUNCATE application.finding, application.report, "
                           "application.engine_run, application.asset"))
        with self._db.session(KNOWLEDGE) as s:
            s.execute(text("TRUNCATE knowledge.kg_edge, knowledge.kg_node"))
        _log.info("simulator_reset")

    def seed(self) -> list[str]:
        """Learn each machine's profile, write a back-filled 30s CSV, ingest it."""
        cfg = self._cfg
        cfg.live_dir.mkdir(parents=True, exist_ok=True)
        if cfg.reset:
            self._wipe()

        units = ProcessedCsvSource(cfg.processed_dir).available_units()
        start = self._live_start - timedelta(days=cfg.backfill_days)

        for unit in units:
            profiles, _ = profile_unit(cfg.processed_dir, unit)
            drift = cfg.drift if (cfg.drift and cfg.drift.unit == unit) else None
            gen = MachineGenerator(unit, profiles, self._live_start, drift)
            self._generators[unit] = gen

            rows = gen.rows_between(start, self._live_start)
            path = cfg.live_dir / _UNIT_FILE_MAP[unit]
            pd.DataFrame(rows).to_csv(path, index=False)
            _log.info("simulator_seeded", extra={"unit": unit, "rows": len(rows)})

        self.ingest_and_analyse(units)
        return units

    # ------------------------------ live ticks ------------------------------

    def append_tick(self, units: list[str], t: datetime) -> None:
        """Append one 30-second row per machine — the CSV keeps growing."""
        for unit in units:
            path = self._cfg.live_dir / _UNIT_FILE_MAP[unit]
            row = self._generators[unit].row(t)
            pd.DataFrame([row]).to_csv(path, mode="a", header=False, index=False)

    def _watermark(self, unit: str) -> datetime | None:
        with self._db.session(SENSOR_HISTORY) as s:
            row = s.execute(
                text("SELECT last_time FROM sensor_history.ingest_watermark WHERE unit = :u"),
                {"u": unit},
            ).one_or_none()
        if row is None:
            return None
        ts = row[0]
        return ts.replace(tzinfo=None) if ts.tzinfo else ts

    def ingest_and_analyse(self, units: list[str]) -> dict[str, int]:
        """Tail each CSV past the watermark -> validate -> persist -> analyse."""
        csv = ProcessedCsvSource(self._cfg.live_dir)
        written: dict[str, int] = {}

        for unit in units:
            series = csv.load(unit)
            self._sensors.upsert_asset(series.asset)  # keeps the DB source able to rebuild it

            mark = self._watermark(unit)
            fresh = [r for r in iter_readings(series, source="live_csv")
                     if mark is None or r.time > mark]
            if not fresh:
                continue

            outcome = ReadingValidation(unit).validate(fresh)
            n = self._sink.write(outcome.accepted)
            written[unit] = n
            if outcome.rejected:
                _log.warning("simulator_rejected",
                             extra={"unit": unit, "rejected": len(outcome.rejected)})

        # Only re-analyse machines that actually received new data.
        for unit in written:
            result = self._analysis.run(unit)
            _log.info("simulator_analysed", extra={
                "unit": unit, "readings": written[unit],
                "findings": result.finding_count, "replayed": result.replayed})
        return written

    # -------------------------------- loop ---------------------------------

    def run_forever(  # pragma: no cover - loop
        self, units: list[str], offset_seconds: float = 1.0
    ) -> None:
        _log.info("simulator_started", extra={"units": len(units), "cadence_s": 30})
        while True:
            now = datetime.now(tz=UTC).replace(tzinfo=None)
            next_tick = align_to_tick(now) + TICK
            # wake just AFTER the tick (e.g. :31) so the row for that second exists
            time.sleep(max(0.0, (next_tick - now).total_seconds() + offset_seconds))

            self.append_tick(units, next_tick)
            self.ingest_and_analyse(units)
