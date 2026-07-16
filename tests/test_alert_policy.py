"""Pins the escalation policy's edge cases (see alerting/policy.py docstring)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from senseminds.alerting import Alert, AlertKind, AlertPolicy, AlertStatus
from senseminds.domain.enums import Severity
from senseminds.domain.value_objects import Confidence, Evidence, Provenance
from senseminds.findings import (
    Finding,
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
    ObservedWindow,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
POLICY = AlertPolicy(reminder=timedelta(minutes=30), cooldown=timedelta(minutes=15))


def _finding(identity: str, severity: Severity = Severity.CRITICAL) -> Finding:
    return Finding(
        finding_id=f"fid-{identity}-{severity.value}",
        identity_key=identity,
        finding_type=FindingType.THRESHOLD_CRITICAL,
        category=FindingCategory.THRESHOLD,
        scope=FindingScope.SENSOR,
        origin=FindingOrigin.DERIVED,
        summary="Discharge Pressure past its critical setpoint",
        detail="Reading exceeded the protection setpoint.",
        target_key="SC-126:discharge_pressure",
        equipment_key="SC-126",
        severity=severity,
        confidence=Confidence(value=0.95, rationale="protection setpoint breached"),
        evidence=(Evidence(artifact_id="a1", description="observed", observed_value=284.2),),
        source_engine="threshold",
        observed_window=ObservedWindow(start=None, end=None),
        provenance=Provenance(
            engine="threshold", engine_version="1", source_unit="SC-126",
            input_hash="h", produced_at=NOW,
        ),
    )


def _alert(identity: str, kind: AlertKind, age: timedelta,
           status: AlertStatus = AlertStatus.SENT) -> Alert:
    return Alert(
        alert_id=f"a-{identity}-{kind.value}", unit="SC-126", identity_key=identity,
        finding_id=f"fid-{identity}", kind=kind, severity="critical",
        subject="s", status=status, created_at=NOW - age,
    )


def _decide(previous=(), observed=(), latest=None):
    return POLICY.decide(
        unit="SC-126", display_name="Screw Compressor 126",
        previous=tuple(previous), observed=tuple(observed),
        latest=latest or {}, now=NOW,
    )


class TestTriggered:
    def test_new_critical_triggers(self) -> None:
        alerts = _decide(observed=[_finding("k1")])
        assert [(a.kind, a.status) for a in alerts] == [
            (AlertKind.TRIGGERED, AlertStatus.PENDING)
        ]

    def test_warning_never_alerts(self) -> None:
        assert _decide(observed=[_finding("k1", Severity.WARNING)]) == []

    def test_escalation_warning_to_critical_triggers(self) -> None:
        alerts = _decide(previous=[_finding("k1", Severity.WARNING)],
                         observed=[_finding("k1")])
        assert alerts[0].kind is AlertKind.TRIGGERED

    def test_preexisting_critical_with_no_alert_history_is_announced_once(self) -> None:
        # Critical since before the alerting system existed (edge 6).
        alerts = _decide(previous=[_finding("k1")], observed=[_finding("k1")])
        assert [(a.kind, a.status) for a in alerts] == [
            (AlertKind.TRIGGERED, AlertStatus.PENDING)
        ]


class TestFlapping:
    def test_retrigger_within_cooldown_is_suppressed_but_recorded(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.RESOLVED, age=timedelta(minutes=5))}
        alerts = _decide(observed=[_finding("k1")], latest=latest)
        assert [(a.kind, a.status) for a in alerts] == [
            (AlertKind.TRIGGERED, AlertStatus.SUPPRESSED)
        ]

    def test_retrigger_after_cooldown_is_emailed(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.RESOLVED, age=timedelta(minutes=20))}
        alerts = _decide(observed=[_finding("k1")], latest=latest)
        assert alerts[0].status is AlertStatus.PENDING

    def test_resolution_of_suppressed_trigger_is_also_suppressed(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.TRIGGERED, age=timedelta(minutes=2),
                               status=AlertStatus.SUPPRESSED)}
        alerts = _decide(previous=[_finding("k1")], latest=latest)
        assert [(a.kind, a.status) for a in alerts] == [
            (AlertKind.RESOLVED, AlertStatus.SUPPRESSED)
        ]


class TestReminder:
    def test_still_critical_past_interval_reminds(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.TRIGGERED, age=timedelta(minutes=45))}
        alerts = _decide(previous=[_finding("k1")], observed=[_finding("k1")],
                         latest=latest)
        assert [(a.kind, a.status) for a in alerts] == [
            (AlertKind.REMINDER, AlertStatus.PENDING)
        ]

    def test_still_critical_within_interval_stays_quiet(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.TRIGGERED, age=timedelta(minutes=10))}
        assert _decide(previous=[_finding("k1")], observed=[_finding("k1")],
                       latest=latest) == []

    def test_reminders_repeat(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.REMINDER, age=timedelta(minutes=31))}
        alerts = _decide(previous=[_finding("k1")], observed=[_finding("k1")],
                         latest=latest)
        assert alerts[0].kind is AlertKind.REMINDER


class TestResolved:
    def test_severity_drop_resolves(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.TRIGGERED, age=timedelta(minutes=5))}
        alerts = _decide(previous=[_finding("k1")],
                         observed=[_finding("k1", Severity.WARNING)], latest=latest)
        assert [(a.kind, a.status) for a in alerts] == [
            (AlertKind.RESOLVED, AlertStatus.PENDING)
        ]

    def test_condition_vanishing_entirely_resolves(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.TRIGGERED, age=timedelta(minutes=5))}
        alerts = _decide(previous=[_finding("k1")], observed=[], latest=latest)
        assert alerts[0].kind is AlertKind.RESOLVED

    def test_never_announced_clears_silently(self) -> None:
        # Was critical, cleared, but no alert was ever recorded (edge 5).
        assert _decide(previous=[_finding("k1")], observed=[]) == []

    def test_already_resolved_does_not_resolve_again(self) -> None:
        latest = {"k1": _alert("k1", AlertKind.RESOLVED, age=timedelta(minutes=5))}
        assert _decide(previous=[_finding("k1")], observed=[], latest=latest) == []


class TestCascade:
    def test_multiple_criticals_each_get_an_alert(self) -> None:
        alerts = _decide(observed=[_finding("k1"), _finding("k2"), _finding("k3")])
        assert len(alerts) == 3
        assert {a.identity_key for a in alerts} == {"k1", "k2", "k3"}

    def test_wording_change_while_critical_does_not_retrigger(self) -> None:
        # Same identity, new finding_id (edge 7): the reminder cycle owns it.
        latest = {"k1": _alert("k1", AlertKind.TRIGGERED, age=timedelta(minutes=5))}
        assert _decide(previous=[_finding("k1")], observed=[_finding("k1")],
                       latest=latest) == []

    def test_payload_carries_the_report_content(self) -> None:
        alert = _decide(observed=[_finding("k1")])[0]
        assert alert.payload["summary"].startswith("Discharge Pressure")
        assert alert.payload["evidence"][0]["observed_value"] == 284.2
        assert alert.subject.startswith("[SenseMinds 360] CRITICAL")
