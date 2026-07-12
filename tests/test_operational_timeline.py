"""Operational Timeline engine - behaviour (edge cases) and contract tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from senseminds.engines.operating_state import OperatingStateEngine, OperatingStateResult
from senseminds.engines.operational_timeline import (
    MachineTimeline,
    OperationalTimelineEngine,
    OperationalTimelineResult,
    TimelineEvent,
)
from senseminds.ingestion import ProcessedCsvSource


def _states(tmp_path: Path, loading: list[float]) -> OperatingStateResult:
    n = len(loading)
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame(
        {"timestamp": [t.isoformat() for t in ts], "Loading Percentage": loading}
    ).to_csv(tmp_path / "SC-126.csv", index=False)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    return OperatingStateEngine().compute(series)


# ----------------------------- behaviour -----------------------------

def test_events_and_segments_from_bimodal_history(tmp_path: Path) -> None:
    states = _states(tmp_path, [0.0] * 100 + [100.0] * 100)
    tl = OperationalTimelineEngine().compute(states).machine("Compressor")
    assert len(tl.events) > 0
    types = {e.event_type for e in tl.events}
    assert "entered_full_load" in types
    assert {"running", "idle"} & {s.segment_type for s in tl.segments}
    # state durations reused from the state engine (not recomputed)
    assert len(tl.state_durations) == len({e.state for e in tl.events})


def test_not_segmentable_machine_is_handled(tmp_path: Path) -> None:
    states = _states(tmp_path, [100.0] * 5)  # < 30 points -> not segmentable
    tl = OperationalTimelineEngine().compute(states).machine("Compressor")
    assert tl.events == ()
    assert tl.runtime is None
    assert "Not segmentable" in tl.metadata.note


def test_min_event_minutes_filters_events_but_not_segments(tmp_path: Path) -> None:
    states = _states(tmp_path, [0.0] * 100 + [100.0] * 100)
    full = OperationalTimelineEngine().compute(states).machine("Compressor")
    filtered = (
        OperationalTimelineEngine(min_event_minutes=10_000).compute(states).machine("Compressor")
    )
    assert len(filtered.events) < len(full.events)
    # segments/runtime are unaffected by the event filter (durations stay exact)
    assert len(filtered.segments) == len(full.segments)


def test_negative_min_event_rejected() -> None:
    with pytest.raises(ValueError, match="min_event_minutes"):
        OperationalTimelineEngine(min_event_minutes=-1)


def test_threshold_context_flows_into_evidence(tmp_path: Path) -> None:
    from senseminds.engines.operating_envelope import OperatingEnvelopeEngine
    from senseminds.engines.statistics import StatisticsEngine
    from senseminds.engines.threshold import ThresholdEngine

    n = 200
    ts = pd.date_range("2024-01-01", periods=n, freq="30min")
    pd.DataFrame(
        {
            "timestamp": [t.isoformat() for t in ts],
            "Loading Percentage": [0.0] * 100 + [100.0] * 100,
            "Discharge Pressure": [200.0] * n,  # below operating 235-247 -> breaches
        }
    ).to_csv(tmp_path / "SC-126.csv", index=False)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    states = OperatingStateEngine().compute(series)
    env = OperatingEnvelopeEngine().compute(series, StatisticsEngine().compute(series))
    thr = ThresholdEngine().compute(series, env)

    tl = OperationalTimelineEngine().compute(states, thr).machine("Compressor")
    assert any("discharge_pressure" in e.evidence.threshold_context for e in tl.events)


def test_unit_mismatch_raises(tmp_path: Path) -> None:
    from senseminds.engines.exceptions import EngineInputError
    from senseminds.engines.operating_envelope import OperatingEnvelopeEngine
    from senseminds.engines.statistics import StatisticsEngine
    from senseminds.engines.threshold import ThresholdEngine

    states = _states(tmp_path, [0.0] * 100 + [100.0] * 100)
    series = ProcessedCsvSource(tmp_path).load("SC-126")
    env = OperatingEnvelopeEngine().compute(series, StatisticsEngine().compute(series))
    thr = ThresholdEngine().compute(series, env).model_copy(update={"unit": "COM-102"})
    with pytest.raises(EngineInputError, match="does not match"):
        OperationalTimelineEngine().compute(states, thr)


# ----------------------------- contract -----------------------------

def test_result_is_immutable(tmp_path: Path) -> None:
    states = _states(tmp_path, [0.0] * 100 + [100.0] * 100)
    result = OperationalTimelineEngine().compute(states)
    with pytest.raises(ValidationError):
        result.unit = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        result.machines[0].events[0].duration_minutes = 1.0  # type: ignore[misc]


def test_serialization_round_trip(tmp_path: Path) -> None:
    states = _states(tmp_path, [0.0] * 100 + [100.0] * 100)
    result = OperationalTimelineEngine().compute(states)
    restored = OperationalTimelineResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_schema_is_stable() -> None:
    assert set(TimelineEvent.model_fields) == {
        "event_type", "state", "start", "end", "duration_minutes", "evidence",
    }
    assert set(MachineTimeline.model_fields) == {
        "machine_label", "events", "segments", "state_durations", "runtime", "metadata",
    }


def test_provenance_carries_engine_version(tmp_path: Path) -> None:
    states = _states(tmp_path, [0.0] * 100 + [100.0] * 100)
    result = OperationalTimelineEngine().compute(states)
    assert result.provenance.engine == "operational_timeline"
    assert result.provenance.engine_version == "0.1.0"
