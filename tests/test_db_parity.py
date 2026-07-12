"""Storage-transition parity (ADR-019 D2).

The success criterion: engines produce byte-identical output whether a unit is
loaded from the processed CSV or reconstructed from TimescaleDB. Integration
test - skipped unless a Postgres/TimescaleDB is reachable (set
``SENSEMINDS_DATABASE_URL``) and the processed CSVs are present.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy
from senseminds.application.pipeline import DeterministicPipeline
from senseminds.config import Settings
from senseminds.ingestion import DbTimeSeriesSource, ProcessedCsvSource

_ROOT = Path(__file__).resolve().parents[2] / "Datasets"
_PROCESSED = _ROOT / "processed"
_UNIT = "SC-126"
_ENGINES = (
    "quality", "statistics", "operating_state", "envelope",
    "threshold", "timeline", "reliability",
)


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


pytestmark = pytest.mark.skipif(
    not (_PROCESSED / f"{_UNIT}.csv").exists() or not _db_available(_db_url()),
    reason="TimescaleDB or processed CSV not available",
)


@pytest.fixture(scope="module")
def db():  # noqa: ANN201
    from senseminds.application.bootstrap import bootstrap_units
    from senseminds.infrastructure.db import build_database
    from senseminds.infrastructure.db.migrate import upgrade

    url = _db_url()
    upgrade(url)  # idempotent
    database = build_database(Settings(database_url=url))
    bootstrap_units(database, _PROCESSED, units=[_UNIT])  # idempotent
    yield database
    database.dispose()


def _payload(result) -> dict:  # noqa: ANN001
    dumped = result.model_dump()
    dumped.pop("provenance")  # provenance carries a wall-clock produced_at
    return dumped


def test_reconstructed_asset_is_identical(db) -> None:  # noqa: ANN001
    csv = ProcessedCsvSource(_PROCESSED).load(_UNIT)
    dbs = DbTimeSeriesSource(db).load(_UNIT)
    assert csv.asset == dbs.asset


def test_reconstructed_frame_is_byte_identical(db) -> None:  # noqa: ANN001
    csv = ProcessedCsvSource(_PROCESSED).load(_UNIT)
    dbs = DbTimeSeriesSource(db).load(_UNIT)
    assert len(csv.frame) == len(dbs.frame)
    csv_sf = csv.sensor_frame().reset_index(drop=True)
    db_sf = dbs.sensor_frame()[list(csv.manifest.sensor_keys)].reset_index(drop=True)
    pd.testing.assert_frame_equal(csv_sf, db_sf, check_exact=True)
    assert csv.timestamps.reset_index(drop=True).equals(dbs.timestamps.reset_index(drop=True))


def test_all_engine_outputs_are_byte_identical(db) -> None:  # noqa: ANN001
    csv_ctx = DeterministicPipeline().run(ProcessedCsvSource(_PROCESSED).load(_UNIT))
    db_ctx = DeterministicPipeline().run(DbTimeSeriesSource(db).load(_UNIT))
    for name in _ENGINES:
        csv_result = getattr(csv_ctx, name)
        db_result = getattr(db_ctx, name)
        assert _payload(csv_result) == _payload(db_result), f"{name} payload differs"
        assert (
            csv_result.provenance.input_hash == db_result.provenance.input_hash
        ), f"{name} input_hash differs"
