# SenseMinds 360 — Backend API Reference

**For frontend developers.** Every endpoint below is live; every example response
was captured from the running system, not written by hand.

- Base URL: `{HOST}/api/v1` (ops endpoints are at the root, not under `/api/v1`)
- Format: JSON in, JSON out. `Content-Type: application/json` on every POST with a body
  — **except** `/auth/token`, which is form-encoded (OAuth2 standard).
- Interactive spec: **`{HOST}/docs`** (Swagger UI) and **`{HOST}/openapi.json`**.
  These are generated from the code, so they are never out of date.

---

## 1. Authentication

All `/api/v1` endpoints except `/auth/token` require a **Bearer token**.

### `POST /api/v1/auth/token` — log in

Form-encoded (`application/x-www-form-urlencoded`), **not** JSON.

```
username=admin&password=admin
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Send it on every subsequent call:

```
Authorization: Bearer <access_token>
```

Token lifetime is 720 minutes (12 h) by default — configurable via
`SENSEMINDS_ACCESS_TOKEN_TTL_MINUTES`.

### `GET /api/v1/auth/me` — who am I

```json
{ "username": "admin", "roles": ["admin"] }
```

Use this on app boot to validate a stored token and to drive role-based UI.

### Roles

| Role | Can do |
|---|---|
| `admin` | everything, including `POST /alerts/test` |
| `reliability_engineer` | all read endpoints, trigger analysis |
| `maintenance_engineer` | all read endpoints, trigger analysis |

`admin` implicitly satisfies every role check.

### Error contract

| Status | Meaning | Frontend should |
|---|---|---|
| `401` | missing / expired / invalid token | clear the token, redirect to login |
| `403` | authenticated but role not permitted | show "not permitted", don't log out |
| `404` | unknown unit | show "machine not found" |
| `422` | query/body validation failed | fix the request; body names the field |
| `502` | upstream failure (e.g. SMTP) | surface the message, it is human-readable |
| `503` | feature not configured (e.g. SMTP absent) | hide/disable the feature |

`422` bodies name the offending parameter, e.g.:

```json
{"detail":[{"type":"greater_than_equal","loc":["query","points"],
            "msg":"Input should be greater than or equal to 10","input":"3"}]}
```

---

## 2. Assets

### `GET /api/v1/assets` — machine list

Use for the sidebar / fleet grid.

```json
[
  {
    "unit": "COM-102",
    "equipment_class": "utility_air_compressor",
    "display_name": "COM-102",
    "sensor_count": 8
  }
]
```

### `GET /api/v1/assets/{unit}` — one machine, with sensors and subsystems

```json
{
  "unit": "SC-126",
  "equipment_class": "screw_compressor",
  "display_name": "SC-126",
  "sensor_count": 10,
  "sensors": [
    { "key": "suction_pressure", "display_name": "Suction Pressure",
      "sensor_type": "pressure", "unit": { "symbol": "kg/cm2", "assumed": false } }
  ],
  "subsystems": [
    { "key": "compression", "display_name": "Compression",
      "sensor_keys": ["suction_pressure", "discharge_pressure"] }
  ]
}
```

`subsystems` drives the digital-twin layout; `unit.assumed` tells you whether the
engineering unit was inferred rather than specified (show it differently if true).

---

## 3. Findings — the core data model

A **Finding** is an immutable, evidence-backed engineering claim. Findings are
append-only; they are never edited or deleted.

### `GET /api/v1/assets/{unit}/findings`

| Query param | Type | Default | Notes |
|---|---|---|---|
| `origin` | `derived` \| `diagnosed` \| `learned` | all | how it was produced |
| `category` | string | all | `threshold`, `health`, `reliability`, `anomaly`, … |
| `severity` | `ok` \| `info` \| `warning` \| `critical` | all | |
| `history` | boolean | `false` | `false` = current state only; `true` = full history |

**Default (`history=false`) returns the current state** — the newest observation of
each condition the latest analysis still sees. A condition that has cleared drops
out. This is what you want for a dashboard.

```json
{
  "finding_id": "224d3e1d408bc683",
  "identity_key": "253615721127ab11",
  "finding_type": "threshold_critical",
  "category": "threshold",
  "scope": "sensor",
  "origin": "derived",
  "summary": "discharge_pressure reached a critical threshold state",
  "detail": "Latest reading 283.71 breached a protection setpoint.",
  "target_key": "discharge_pressure",
  "equipment_key": "SC-126",
  "subsystem_key": "compression",
  "severity": "critical",
  "confidence": { "value": 1.0, "rationale": "100.0% coverage (9664 of 9664 readings evaluated)." },
  "evidence": [
    { "artifact_id": "SC-126__threshold", "description": "current state critical",
      "observed_value": 283.71 }
  ],
  "source_engine": "threshold",
  "observed_window": { "start": "…", "end": "…" },
  "triggered_by": []
}
```

**Key fields for UI work**

| Field | Use |
|---|---|
| `finding_id` | unique per observation — React key, and what the Copilot cites |
| `identity_key` | stable across observations of the *same* condition — use to correlate over time |
| `origin` | `derived` = measured fact · `diagnosed` = rule-derived cause · `learned` = ML hypothesis (**advisory only — never present as fact**) |
| `severity` | drives colour. Only `critical` triggers alert emails |
| `evidence[]` | always show — this is what makes a claim checkable |
| `triggered_by` | `identity_key`s of findings that caused this diagnosis — renders the reasoning chain |

### `GET /api/v1/assets/{unit}/diagnoses`

Convenience filter: rule-derived (`origin = diagnosed`) findings only. Same shape.

---

## 4. Telemetry — raw sensor series

### `GET /api/v1/assets/{unit}/telemetry`

| Query param | Type | Default | Range |
|---|---|---|---|
| `hours` | number | `6` | ≤ 720 |
| `points` | integer | `90` | 10 – 500 |

Server-side downsampling (TimescaleDB `time_bucket`) — request the number of points
your chart can actually draw, not the raw series.

```json
{
  "unit": "SC-126",
  "hours": 1.0,
  "sensors": [
    {
      "key": "suction_pressure",
      "display_name": "Suction Pressure",
      "unit_symbol": "kg/cm2",
      "latest": { "time": "2026-07-18T08:44:00+00:00", "value": 16.97 },
      "threshold": { "low": 10.0, "high": 30.0 },
      "points": [
        { "t": "2026-07-18T07:42:00+00:00", "v": 16.45 },
        { "t": "2026-07-18T07:48:00+00:00", "v": 16.67 }
      ]
    }
  ]
}
```

`threshold` may be `null` (no configured band) and `low`/`high` may be individually
`null` — guard before drawing band shading.

---

## 5. Predictive Outlook

### `GET /api/v1/assets/{unit}/outlook`

Forward-looking summary. **Not** failure probability or remaining useful life —
those need labelled breakdown history (Phase C) that does not exist yet. Read
`caveat` and render it; it is part of the contract, not decoration.

```json
{
  "unit": "SC-126",
  "display_name": "SC-126",
  "condition_score": 93.6,
  "condition_basis": "Deterministic health score from measured readings (not a model output).",
  "weakest_subsystem": { "key": "compression", "score": 85.3 },
  "soonest": {
    "sensor": "evaporator_entering_temp",
    "hours_ahead": 1.0,
    "bound": 8.0,
    "projected_value": 8.852,
    "model_name": "seasonal_naive",
    "model_version": "0.1.0",
    "backtest_mae": 0.023865,
    "interval_confidence": 0.7917,
    "summary": "…projected to approach its operating limit in ~1.0h (hypothesis)",
    "finding_id": "353505a8429d9f43"
  },
  "forecasts": [ "…same shape, all projected approaches, soonest first…" ],
  "novelty": {
    "score": 1.0, "windows": 10,
    "top_features": [ { "feature": "discharge_pressure", "deviation": 3.4394 } ],
    "model_name": "isolation_forest_novelty",
    "finding_id": "…"
  },
  "critical_count": 3,
  "headline": "3 conditions past a safe limit right now — act on those before anything forecast.",
  "caveat": "This is a trend projection against operating limits — not a failure prediction…",
  "recommendation": "Deal with the 3 critical conditions first: …",
  "recommendation_citations": ["c4d3aeb549694cff", "d5a207014..."]
}
```

`condition_score`, `soonest`, and `novelty` are each **nullable** — a machine with
no health finding, no projected approach, or no novelty signal returns `null`.
Render "—", not `NaN`.

---

## 6. Alerts (escalation)

Alert rows are written in the same transaction as the finding that caused them, then
emailed after commit. Every outcome is recorded, including ones deliberately not sent.

### `GET /api/v1/alerts?limit=100` — recent across all machines
### `GET /api/v1/assets/{unit}/alerts?limit=100` — one machine

`limit`: 1–500, default 100. Newest first.

```json
{
  "alert_id": "0db54918797044118492f29b923f3efd",
  "unit": "SC-126",
  "identity_key": "253615721127ab11",
  "finding_id": "224d3e1d408bc683",
  "kind": "triggered",
  "severity": "critical",
  "subject": "[SenseMinds 360] CRITICAL — SC-126: discharge_pressure reached a critical threshold state",
  "payload": {
    "summary": "discharge_pressure reached a critical threshold state",
    "detail": "Latest reading 283.71 breached a protection setpoint.",
    "target_key": "discharge_pressure",
    "display_name": "SC-126",
    "finding_type": "threshold_critical",
    "severity": "critical",
    "confidence": 1.0,
    "detected_at": "2026-07-18T08:41:33.661010+00:00",
    "evidence": [ { "description": "current state critical", "observed_value": 283.71 } ]
  },
  "status": "sent",
  "attempts": 1,
  "last_error": null,
  "created_at": "2026-07-18T08:41:33+00:00",
  "sent_at": "2026-07-18T08:41:35+00:00"
}
```

`payload` is frozen at decision time — render from it, don't re-fetch the finding.

**`kind`** — where the incident is in its lifecycle:

| Value | Meaning |
|---|---|
| `triggered` | became critical |
| `reminder` | still critical after 30 min, nobody acted |
| `resolved` | cleared |

**`status`** — what happened to the email:

| Value | Meaning | Suggested UI |
|---|---|---|
| `sent` | delivered to SMTP | green "Email sent" |
| `pending` | queued, will retry | grey "Sending…" |
| `failed` | gave up after 5 attempts | red + show `last_error` |
| `suppressed` | flapping — recorded, deliberately not emailed | grey "Muted (flapping)" |
| `skipped` | SMTP not configured | amber "No email set up" |

### `POST /api/v1/alerts/test` — send a real test email (**admin only**)

No body. Sends through the production mailer and template.

```json
{ "sent": true, "to": ["ops@example.com"], "detail": "accepted by SMTP server" }
```

`503` if SMTP is unconfigured; `502` with the real SMTP error if the send fails.

---

## 7. Copilot (grounded LLM)

### `POST /api/v1/llm/query`

```json
{
  "unit": "SC-126",
  "question": "Is this machine safe to run?",
  "persona": "maintenance_engineer",
  "history": [ { "role": "user", "content": "…" }, { "role": "assistant", "content": "…" } ]
}
```

`persona`: `maintenance_engineer` | `reliability_engineer` | `plant_manager` — changes
register and detail, not facts. `history` is presentation-only conversation context
(send the last few turns); it never becomes evidence.

```json
{
  "unit": "SC-126",
  "persona": "maintenance_engineer",
  "answer": "The machine SC-126 is not safe to run due to a critical discharge pressure threshold breach (ref: 224d3e1d408bc683)…",
  "claims": [
    { "text": "discharge_pressure reached a critical threshold state",
      "category": "fact", "citations": ["224d3e1d408bc683"] },
    { "text": "Condenser fouling suspected (equipment:SC-126)",
      "category": "diagnosis", "citations": ["6d6bd2c569a1a688"] }
  ],
  "insufficient": [],
  "citations": ["224d3e1d408bc683", "6d6bd2c569a1a688"],
  "model": "llama-3.3-70b-versatile"
}
```

**Rendering rules that matter:**

- Every `claim.citations[]` entry is a `finding_id` — make them clickable to the finding.
- `category`: `fact` · `diagnosis` · `hypothesis` · `forecast`. Style hypotheses and
  forecasts as tentative; they are not facts.
- `insufficient[]` lists questions the evidence could not answer. Show it — that
  silence is deliberate, not a failure.
- `model` — when it is `deterministic_stub`, no LLM key is configured. Show an
  "offline mode" banner.

Uncited claims are dropped by the backend before you ever see them.

---

## 8. Analysis and audit

### `POST /api/v1/analyze` — trigger an analysis run

```json
{ "unit": "SC-126" }
```
```json
{ "unit": "SC-126", "run_id": "…", "input_hash": "8c8e…", "finding_count": 9, "replayed": false }
```

`replayed: true` means this exact input was already analysed — a no-op, not an error.
Show "No new readings since the last check."

### `GET /api/v1/runs/{unit}` — engine-run audit trail

Run history with status, timings, `finding_count`, engine versions, artifact ids.
**Can be large** — paginate or slice client-side.

### `POST /api/v1/readings` — push readings in (ingestion)

For integrations, not the dashboard.

---

## 9. Knowledge graph

### `GET /api/v1/assets/{unit}/graph`

```json
{ "unit": "SC-126",
  "nodes": [ { "id": "equipment:SC-126", "type": "Equipment", "properties": {} } ],
  "edges": [ { "src": "…", "dst": "…", "type": "HAS_SUBSYSTEM", "properties": {} } ] }
```

**Large payload** (~120 KB for one machine). Fetch only when the graph view opens.

---

## 10. Ops endpoints (no auth, root path)

| Endpoint | Use |
|---|---|
| `GET /health` | liveness — is the process up |
| `GET /ready` | readiness — is the DB reachable. **Use this for load-balancer probes** |
| `GET /metrics` | Prometheus text format |

```
# platform metrics
senseminds_up 1
senseminds_findings_total 8129
senseminds_engine_runs_total 6158
senseminds_kg_nodes_total 3021
```

---

## 11. Frontend integration notes

**Polling cadence.** The backend analyses every 30 s. Match it — faster is wasted work:

| View | Interval |
|---|---|
| Telemetry, outlook, alerts | 30 s |
| Findings / asset detail | 30 s, or on user action |
| Graph, reports, runs | on open only — never poll |

**Payload sizes.** `assets`, `findings`, `telemetry`, `outlook`, `alerts` are small
and safe to poll. `graph` (~120 KB), `reports` and `runs` (hundreds of KB) are not.

**Token handling.** Store the token; attach it to every request; on `401`, clear it and
redirect to login. A `403` is *not* a login failure — do not log the user out.

**Timezones.** All timestamps are UTC ISO-8601 with an explicit offset. Convert for
display; never assume local time.

**Nullability.** Assume nullable and guard: `threshold`, `latest`, `condition_score`,
`soonest`, `novelty`, `weakest_subsystem`, `subsystem_key`, `last_error`, `sent_at`.

**Evidence is the point.** Any UI that shows a conclusion should be able to show the
evidence behind it. `evidence[]` on findings, `citations[]` on Copilot claims, and
`payload.evidence` on alerts all exist for this.

**Learned ≠ fact.** `origin: "learned"` findings, `novelty`, and `forecasts` are
advisory hypotheses. Never render them with the same weight as measured facts — the
backend deliberately never alarms on them alone.
