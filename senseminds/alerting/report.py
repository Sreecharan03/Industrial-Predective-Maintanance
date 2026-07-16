"""The escalation email report — WHAT the recipient reads.

One email per (unit, kind) batch: if a breach cascades into several critical
conditions in the same tick, the recipient gets ONE report listing all of them,
not four emails. Every claim in the report is lifted verbatim from the findings'
evidence — same grounding rule as everywhere else in the platform."""

from __future__ import annotations

import html

from senseminds.alerting.models import Alert, AlertKind

# Mirrors frontend/src/lib/ui.ts PLAIN — what each finding MEANS, for people
# reading email on a phone at 2am, not for engineers at a dashboard.
_PLAIN: dict[str, str] = {
    "threshold_misspecified": "The limit set for this sensor doesn't match how the "
    "machine actually runs. The limit probably needs reviewing — this is not a fault.",
    "threshold_config_review_recommended": "Worth reviewing this limit — it doesn't "
    "reflect how the machine normally operates.",
    "threshold_critical": "A reading has gone past a safety limit. This needs attention now.",
    "health_degraded": "Overall condition is below normal for this machine.",
    "reliability_drift": "This sensor's readings have slowly shifted over time. "
    "It may need calibration.",
    "reliability_flatline": "This sensor has been stuck on the same value — it may "
    "not be reporting properly.",
    "sensor_untrustworthy": "This sensor's readings can't be fully trusted right now.",
    "critical_on_untrustworthy_sensor": "A critical reading came from a sensor we "
    "don't fully trust — check it before acting.",
    "condenser_fouling_suspected": "The condenser may be dirty or blocked.",
    "novelty_elevated": "The machine is behaving unlike its usual pattern. "
    "An early signal, not confirmed.",
    "operating_regime_discovered": "A distinct running mode was spotted in the data.",
    "forecast_threshold_approach": "If the current trend continues, this reading "
    "could reach its limit soon. Advisory only.",
}

_KIND_STYLE = {
    AlertKind.TRIGGERED: ("#BE123C", "CRITICAL — needs attention now"),
    AlertKind.REMINDER: ("#B45309", "STILL CRITICAL — not yet resolved"),
    AlertKind.RESOLVED: ("#15803D", "RESOLVED — condition has cleared"),
}


def subject_for(alerts: list[Alert]) -> str:
    if len(alerts) == 1:
        return alerts[0].subject
    first = alerts[0]
    name = str(first.payload.get("display_name") or first.unit)
    headline = {
        AlertKind.TRIGGERED: "CRITICAL",
        AlertKind.REMINDER: "STILL CRITICAL",
        AlertKind.RESOLVED: "RESOLVED",
    }[first.kind]
    return f"[SenseMinds 360] {headline} — {name}: {len(alerts)} conditions"


def _esc(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


def _confidence(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _condition_card(alert: Alert, colour: str) -> str:
    p = alert.payload
    plain = _PLAIN.get(str(p.get("finding_type", "")), "")
    evidence_rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#57534E;font-size:13px'>"
        f"{_esc(e.get('description'))}</td>"
        f"<td style='padding:4px 0;font-weight:600;font-size:13px;white-space:nowrap'>"
        f"{_esc(e.get('observed_value')) or '—'}</td></tr>"
        for e in p.get("evidence", [])  # type: ignore[union-attr]
    )
    subsystem = p.get("subsystem_key")
    where = _esc(p.get("target_key"))
    if subsystem:
        where += f" &middot; {_esc(subsystem)}"
    meaning = ""
    if plain:
        meaning = (
            "<div style='font-size:13px;color:#44403C;background:#FAFAF9;"
            "border-radius:6px;padding:10px 12px;margin-bottom:10px'>"
            f"<b>What this means:</b> {_esc(plain)}</div>"
        )
    return f"""
    <div style="border:1px solid #E7E5E4;border-left:4px solid {colour};
                border-radius:8px;padding:16px 20px;margin:0 0 14px 0;background:#fff">
      <div style="font-size:15px;font-weight:700;color:#1C1917;margin-bottom:2px">
        {_esc(p.get('summary'))}</div>
      <div style="font-size:12px;color:#78716C;margin-bottom:10px">{where}</div>
      {meaning}
      <div style="font-size:13px;color:#57534E;margin-bottom:10px">{_esc(p.get('detail'))}</div>
      <table style="border-collapse:collapse">{evidence_rows}</table>
      <div style="font-size:11px;color:#A8A29E;margin-top:10px">
        Detected {_esc(str(p.get('detected_at', ''))[:19].replace('T', ' '))} UTC
        &middot; confidence {_confidence(p.get('confidence')):.0%}
        &middot; finding {_esc(alert.finding_id[:16])}</div>
    </div>"""


def build_html(alerts: list[Alert], dashboard_url: str) -> str:
    first = alerts[0]
    colour, banner = _KIND_STYLE[first.kind]
    name = _esc(first.payload.get("display_name") or first.unit)
    cards = "".join(_condition_card(a, colour) for a in alerts)
    unit_link = f"{dashboard_url.rstrip('/')}/assets/{first.unit}"
    return f"""
<div style="font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
            max-width:640px;margin:0 auto;background:#FAFAF9;padding:24px">
  <div style="background:{colour};color:#fff;border-radius:10px 10px 0 0;padding:18px 24px">
    <div style="font-size:12px;letter-spacing:1.5px;opacity:.85">SENSEMINDS 360 &middot;
      ESCALATION</div>
    <div style="font-size:20px;font-weight:800;margin-top:4px">{banner}</div>
    <div style="font-size:15px;margin-top:2px">Machine <b>{name}</b> ({_esc(first.unit)})
      &middot; {len(alerts)} condition{'s' if len(alerts) != 1 else ''}</div>
  </div>
  <div style="background:#F5F5F4;border:1px solid #E7E5E4;border-top:none;
              border-radius:0 0 10px 10px;padding:20px 20px 8px 20px">
    {cards}
    <div style="text-align:center;padding:6px 0 14px 0">
      <a href="{unit_link}" style="display:inline-block;background:#1C1917;color:#fff;
         text-decoration:none;font-size:13px;font-weight:600;padding:10px 22px;
         border-radius:8px">Open {name} on the dashboard</a>
    </div>
  </div>
  <div style="font-size:11px;color:#A8A29E;text-align:center;padding:14px 0 0 0">
    Automated escalation from SenseMinds 360. Every statement above is grounded in a
    recorded finding — reply is not monitored.</div>
</div>"""


def build_text(alerts: list[Alert], dashboard_url: str) -> str:
    """Plain-text alternative for clients that refuse HTML."""
    first = alerts[0]
    _, banner = _KIND_STYLE[first.kind]
    name = str(first.payload.get("display_name") or first.unit)
    lines = [f"SenseMinds 360 escalation — {banner}", f"Machine: {name} ({first.unit})", ""]
    for a in alerts:
        p = a.payload
        lines.append(f"* {p.get('summary')}")
        lines.append(f"  Where: {p.get('target_key')}")
        plain = _PLAIN.get(str(p.get("finding_type", "")))
        if plain:
            lines.append(f"  Meaning: {plain}")
        for e in p.get("evidence", []):  # type: ignore[union-attr]
            value = e.get("observed_value")
            lines.append(f"  - {e.get('description')}: {value if value is not None else '—'}")
        lines.append(f"  Detected: {str(p.get('detected_at', ''))[:19]} UTC")
        lines.append("")
    lines.append(f"Dashboard: {dashboard_url.rstrip('/')}/assets/{first.unit}")
    return "\n".join(lines)
