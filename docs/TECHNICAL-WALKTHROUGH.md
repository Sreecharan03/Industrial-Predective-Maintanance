# SenseMinds 360 — Technical Walkthrough

**Layer-by-layer processing, data storage, and scenario dry runs**

Every table, query result and JSON payload in this document was taken from the
running production stack while writing it. Nothing is illustrative; where a
number appears, it is the number the system actually held at that moment.

Captured: **20 July 2026, 06:00–06:05 UTC** · 6 machines · 750,827 sensor readings
· 231 automated tests passing.

---

## 1. What the system is

A predictive-maintenance platform for six utility machines at Laurus Labs — three
refrigeration screw compressors, two air compressors, and a nitrogen PSA plant.

It ingests sensor data every 30 seconds, computes deterministic engineering
facts, stores what those facts *mean* in a knowledge graph, layers unsupervised
machine learning on top to catch what rules cannot anticipate, and explains the
result in natural language with every claim traceable to recorded evidence.

The governing design rule, which the rest of this document keeps demonstrating:

> **Machine learning is strictly additive.** Deterministic facts are
> authoritative. ML produces hypotheses that are advisory only and can never
> raise an alarm by themselves. Remove the entire ML layer and nothing
> deterministic changes.

---

## 2. Data storage

### 2.1 One database, three schemas

The most common misreading of this architecture is that it uses several
databases. It does not. There is **one PostgreSQL 16 instance with the
TimescaleDB extension**, containing **three logical schemas**:

| Schema | Purpose | Tables |
|---|---|---|
| `sensor_history` | Raw measurements, time-series optimised | `sensor_reading`, `unit_sensor`, `ingest_watermark` |
| `knowledge` | The knowledge graph — what conditions *mean* | `kg_node`, `kg_edge` |
| `application` | Findings, alerts, labels, audit | `asset`, `finding`, `alert`, `feedback`, `engine_run`, `report`, `model_registry`, `rule_version`, `app_user`, `role` |

Live row counts at capture time:

| Schema | Table | Rows |
|---|---|---|
| sensor_history | sensor_reading | **750,827** |
| sensor_history | unit_sensor | 77 |
| sensor_history | ingest_watermark | 6 |
| knowledge | kg_node | 3,234 |
| knowledge | kg_edge | 3,649 |
| application | finding | 8,503 |
| application | engine_run | 6,660 |
| application | report | 6,660 |
| application | alert | 39 |
| application | feedback | 4 |
| application | asset | 6 |
| application | model_registry | 3 |

### 2.2 Why one instance rather than three databases

Each store resolves its **own connection URL**, defaulting to a shared one:

```
SENSEMINDS_DATABASE_URL        = postgresql+psycopg://…/senseminds
SENSEMINDS_SENSOR_HISTORY_URL  = (unset → falls back to DATABASE_URL)
SENSEMINDS_KNOWLEDGE_URL       = (unset → falls back to DATABASE_URL)
SENSEMINDS_APPLICATION_URL     = (unset → falls back to DATABASE_URL)
```

Splitting any store onto its own physical server later is therefore a
**configuration change, not a code change**. Today one instance is correct: a
single plant, one operations team, and — critically — the ability to write a
finding and its graph projection inside **one transaction** (§7).

### 2.3 Why the knowledge graph is not Neo4j

The graph is two tables in the `knowledge` schema, behind a
`KnowledgeGraphRepository` interface with two implementations (in-memory for
tests, PostgreSQL for production).

A dedicated graph database was rejected for current scale: 3,234 nodes and 3,649
edges is trivially served by indexed Postgres, and a second database engine would
have cost a second operational surface, a second backup story, and — the decisive
point — **cross-database transactions**, which would have made it impossible to
commit a finding and its graph projection atomically.

The interface exists precisely so that migrating to Neo4j, when multi-plant scale
justifies it, replaces one class.

### 2.4 TimescaleDB: what it actually buys

`sensor_reading` is a **hypertable** — Postgres transparently partitions it into
week-long chunks:

```
 hypertable_name |    chunk_name    |      range_start       |       range_end        | is_compressed
-----------------+------------------+------------------------+------------------------+---------------
 sensor_reading  | _hyper_1_1_chunk | 2026-07-09 00:00:00+00 | 2026-07-16 00:00:00+00 | f
 sensor_reading  | _hyper_1_2_chunk | 2026-07-16 00:00:00+00 | 2026-07-23 00:00:00+00 | f
```

Three consequences:

1. **Queries prune by time.** A 6-hour dashboard query touches one chunk, not
   750,827 rows.
2. **Compression after 7 days**, segmented by `(unit, sensor_key)` — a policy is
   installed and runs automatically.
3. **`time_bucket()` downsampling** happens in the database. The telemetry
   endpoint returns 90 points from tens of thousands of rows without moving them
   into Python.

> A diagnostic note for anyone inspecting the database: `pg_stat_user_tables`
> reports `sensor_reading` as **0 rows**. That is expected — the rows live in the
> chunks, not the parent table. `SELECT count(*)` returns the true 750,827.

---

## 3. The five layers and what passes between them

Each layer hands the next a **typed object**, not a database query. This is what
keeps the engines independent and individually testable.

| # | Layer | Reads | Produces | Persists to |
|---|---|---|---|---|
| 1 | Data foundation | CSV / REST / historian | `Reading` + `ReadingValidation` | `sensor_history` |
| 2 | Deterministic analytics | `IngestedSeries` | 7 typed engine results → `Finding` | `application.finding` |
| 3 | Knowledge graph | `Finding` | Nodes + edges | `knowledge` |
| 4 | Machine learning | `FeatureFrame` | `PatternResult` (LEARNED findings) | both |
| 5 | Reasoning / LLM | Findings + graph | `GroundedAnswer` | not persisted |

### 3.1 Layer 1 — Data foundation

Readings are validated before storage: missing values, duplicates, timestamp
correction, unit conversion, sensor quality.

```
          time          |  unit  |     sensor_key     | value  | quality |  source
------------------------+--------+--------------------+--------+---------+----------
 2026-07-20 06:02:00+00 | SC-126 | suction_pressure   |  16.39 |       0 | live_csv
 2026-07-20 06:02:00+00 | SC-126 | discharge_pressure | 280.05 |       0 | live_csv
 2026-07-20 06:02:00+00 | SC-126 | oil_pressure       | 185.49 |       0 | live_csv
```

A **sensor catalog** maps each machine's raw column headings to canonical keys.
This table exists because thresholds are configured against the plant's own
column names, while the platform reasons in normalised keys:

```
  unit  |     sensor_key     |   source_column    | ordinal
--------+--------------------+--------------------+---------
 SC-126 | suction_pressure   | Suction Pressure   |       0
 SC-126 | discharge_pressure | Discharge Pressure |       1
 SC-126 | oil_pressure       | Oil Pressure       |       2
```

A **watermark** per machine records the last ingested timestamp, so each cycle
processes only new data:

```
      unit      |       last_time
----------------+------------------------
 COM-102        | 2026-07-20 06:02:00+00
 COM-110        | 2026-07-20 06:02:00+00
 COM103 & NP102 | 2026-07-20 06:02:00+00
```

**Handoff to Layer 2:** `DbTimeSeriesSource` reads the schema and returns an
`IngestedSeries` — a pandas frame plus an asset manifest. Layer 2 never issues SQL.

### 3.2 Layer 2 — Deterministic analytics

Seven engines run as pure functions. Same input always produces byte-identical
output, which is what makes every conclusion auditable.

| Engine | Question |
|---|---|
| Quality | Is this reading trustworthy enough to reason from? |
| Statistics | What is normal for this sensor on this machine? |
| Operating state | Running, idle, or stopped? |
| Operating envelope | Inside its designed envelope? |
| Threshold | Has a value crossed a specification or protection setpoint? |
| Operational timeline | How has behaviour evolved over the period? |
| Reliability | Is the sensor itself drifting, stuck, or degrading? |

Engine results are assembled into **Findings** — immutable, evidence-backed
claims. Here is a real one, exactly as stored:

```json
{
  "finding_id": "7a2b317cca6cd33b",
  "identity_key": "253615721127ab11",
  "finding_type": "threshold_critical",
  "category": "threshold",
  "scope": "sensor",
  "origin": "derived",
  "summary": "discharge_pressure reached a critical threshold state",
  "detail": "Latest reading 280.45 breached a protection setpoint.",
  "target_key": "discharge_pressure",
  "equipment_key": "SC-126",
  "subsystem_key": "compression",
  "severity": "critical",
  "confidence": {
    "value": 1.0,
    "rationale": "100.0% coverage (9758 of 9758 readings evaluated)."
  },
  "evidence": [
    { "artifact_id": "SC-126__threshold",
      "description": "current state critical",
      "observed_value": 280.45 }
  ],
  "provenance": {
    "engine": "findings",
    "engine_version": "0.1.0",
    "input_hash": "d6cb92c32cf6af9e",
    "produced_at": "2026-07-20T06:01:03.495310Z",
    "source_unit": "SC-126"
  }
}
```

Two identifiers do different jobs, and the distinction runs through the whole
system:

- **`finding_id`** = `hash(identity_key, input_hash)` — unique to *this
  observation*. New every time the data changes.
- **`identity_key`** — stable for *this condition*, unchanged across observations.

Findings are **append-only, enforced by a database trigger** that rejects UPDATE
and DELETE. The record of what the platform believed, and when, cannot be
rewritten.

Current mix across all machines:

```
  origin   | count
-----------+-------
 derived   |  7663   (measured facts)
 diagnosed |   723   (rule-derived causes)
 learned   |   117   (ML hypotheses)
```

That ratio is the architecture visible in data: the deterministic layer carries
the load; ML contributes a small number of advisory signals.

### 3.3 Layer 3 — Knowledge graph

Findings are projected into a graph that stores *engineering meaning*, never
sensor values.

```
      node_type       | count            edge_type   | count
----------------------+-------         ---------------+-------
 artifact_ref         |  2577           has_evidence  |  2606
 discovered_pattern   |   501           discovered_by |   501
 sensor               |    77           suggests      |   388
 finding_condition    |    45           has_sensor    |    77
 subsystem            |    26           observed_on   |    45
 threshold_definition |    21           has_subsystem |    26
 equipment            |     6           governed_by   |    21
 learned_model        |     3           triggered_by  |     7
 engineer_validation  |     2           validated_by  |     2
```

The critical finding above appears in the graph as:

```
            src             |               dst                |  edge_type
----------------------------+----------------------------------+--------------
 condition:253615721127ab11 | sensor:SC-126:discharge_pressure | observed_on
 condition:253615721127ab11 | artifact:SC-126__threshold       | has_evidence
```

Read as a sentence: *this condition was observed on SC-126's discharge pressure
sensor, and the evidence for it is the threshold engine's artifact.*

`triggered_by` edges are the auditable reasoning chain — when the rule engine
diagnoses condenser fouling, that edge records exactly which findings caused it.

**Projection is idempotent.** Node properties are replaced wholesale on upsert.
This matters enormously and is revisited in §5.4.

### 3.4 Layer 4 — Machine learning

Models never consume raw readings. A deterministic `FeaturePipeline` builds
per-window feature vectors from validated data: windowed aggregates,
z-normalised for scale-free comparison, weighted by each sensor's reliability
score so an untrustworthy sensor contributes less.

Three models run in production:

| Model | Purpose | Output |
|---|---|---|
| Isolation Forest | "This window is unlike this machine's history" | `novelty_elevated` |
| Gaussian Mixture | Multivariate operating regimes | `operating_regime_discovered` |
| Forecasting (backtest-selected) | Lead time before a limit | `forecast_threshold_approach` |

Everything they emit is marked `origin = learned` and carries
`status = hypothesis`. Forecasting will not promote a complex model unless it
beats the simple baseline by a margin under walk-forward backtesting.

Phase B is **throttled** — it looks for slow trends, so it runs on its own slower
cadence rather than every 30 seconds. The `engine_run.learned` flag records which
cycles included it:

```
              run_id              |      unit      |  input_hash  |  status   | finding_count | learned
----------------------------------+----------------+--------------+-----------+---------------+---------
 998e91a0ea814df8916ab94c72a4e9b8 | COM103 & NP102 | bc83ae574f5a | completed |             3 | f
 1820ceb8644541ebbb94592bef9be925 | COM-110        | 44cb5c480b1b | completed |             3 | f
 181e21d5ee6843609d3393c678dea826 | COM-102        | 3aac283b8f83 | completed |             4 | f
 a279c5583c414212b74eb2617312d747 | SC-104         | 321a95f8fdb2 | completed |             2 | f
```

### 3.5 Layer 5 — Reasoning and LLM

The LLM is a **constrained narrator**, not a reasoner. It receives structured
evidence and must cite it; a `CitationValidator` deletes any claim not backed by
a finding id before the response is returned.

A real query, run live:

**Question:** *"What is wrong with this machine right now?"*

```json
{
  "unit": "SC-126",
  "persona": "maintenance_engineer",
  "answer": "The machine SC-126 is currently experiencing several issues. The
             discharge pressure has reached a critical threshold state with a
             reading of 281.55, which has breached a protection setpoint
             (ref: bf9973c17bf65bde). The overall health of the equipment is
             reduced…",
  "claims": [ "…8 claims, each with citations…" ],
  "model": "groq"
}
```

Eight claims, every one carrying a `finding_id` traceable to a row in
`application.finding`. Claims are categorised `fact` / `diagnosis` /
`hypothesis` / `forecast`, so the interface can present a measured fact
differently from an ML hypothesis.

---

## 4. Scenario dry runs

Six traces through the live system. Each follows one value from sensor to screen.

### Scenario 1 — Normal cycle, nothing wrong

**06:02:11** — the simulator writes a new row for `COM103 & NP102`.

1. **L1** Reading validated, stored, watermark advanced to `06:02:00`.
2. **L2** `DbTimeSeriesSource` loads only new data. Seven engines run.
   `input_hash = bc83ae574f5a`.
3. **L2** Three findings assembled — all previously seen and unchanged.
4. **Material-change filter** compares each against the current view: severity
   equal, wording equal, values within tolerance → **nothing is written**.
5. **L3** No new projection.
6. `engine_run` records `finding_count = 3`, `observed_identities = [3 keys]`,
   `learned = f`.

**Why this matters.** Findings are append-only and `finding_id` derives from the
input hash, so without this filter every 30-second tick would write a fresh row
for a condition that has not changed. This was a real production defect: 4,006
rows accumulated for 25 conditions (~2,532/hour) before the filter was added.
Four of the six machines now write **zero** rows per cycle.

The subtlety that made it work: engines embed numbers in prose ("health is
reduced (86.8)"), so a naive text comparison always differed. The comparator
strips digits before comparing wording, then compares values numerically with a
2% relative tolerance.

### Scenario 2 — Critical breach → email in 2 seconds

The system's headline path, captured live.

| Time | Event | Layer | Persisted |
|---|---|---|---|
| 05:57:00 | `discharge_pressure = 281.x` crosses the 280 protection setpoint | L1 | `sensor_reading` |
| 05:57:03 | Threshold engine returns `CRITICAL`; findings assembled | L2 | — |
| 05:57:03 | 3 findings written: pressure critical, compression health, equipment health | L2 | `application.finding` |
| 05:57:03 | Graph projection: condition nodes + `observed_on` / `has_evidence` edges | L3 | `knowledge` |
| 05:57:03 | Alert policy: 3 conditions newly critical → 3 alert rows, **same transaction** | — | `application.alert` |
| 05:57:05 | Post-commit dispatcher groups them into **one** email; Gmail accepts | — | `status = sent` |

The health cascade is not three separate faults — it is one pressure breach
propagating up the asset hierarchy (sensor → subsystem → equipment), which is why
they are grouped into a single email rather than three.

**Latency: one analysis tick.** The breach at 05:57:00 was in an inbox by
05:57:05.

### Scenario 3 — Flapping, and the emails that were deliberately not sent

This occurred unprompted during document capture, and is the clearest evidence
the escalation policy is doing real work.

SC-126's discharge pressure oscillated across its 280 setpoint:

```
    t     | value
----------+--------
 05:58:30 | 278.79     ← below
 05:59:00 | 280.74     ← above
 05:59:30 | 279.99     ← below
 06:00:00 | 282.70     ← above
 06:00:30 | 279.82     ← below
 06:01:00 | 280.45     ← above
 06:01:30 | 281.63     ← above
 06:02:00 | 280.05     ← above
 06:02:30 | 279.12     ← below
```

A naive implementation would have sent an email on every crossing. What the
platform actually did, for one condition:

```
    at    |   kind    |   status
----------+-----------+------------
 05:57:03 | triggered | sent          ← engineer notified
 05:58:33 | resolved  | sent          ← engineer told it cleared
 05:59:03 | triggered | suppressed    ← re-triggered inside 15-min cooldown
 05:59:33 | resolved  | suppressed    ← its trigger was never emailed
 06:00:03 | triggered | suppressed
 06:00:33 | resolved  | suppressed
 06:01:03 | triggered | suppressed
 06:02:34 | resolved  | suppressed
 06:03:03 | triggered | suppressed
```

Across all conditions in that window: **6 emails sent, 21 suppressed.**

Three deliberate behaviours are visible:

1. **Cooldown.** A condition re-triggering within 15 minutes of its own
   resolution is flapping, not a new incident.
2. **Suppressed ≠ discarded.** Every suppressed alert is stored and shown in the
   interface. The engineer can see the instability without their inbox filling.
3. **Paired suppression.** A `resolved` whose `triggered` was suppressed is also
   suppressed — the system never sends "resolved" for an incident nobody was told
   about.

### Scenario 4 — The platform declining to raise an alarm

`threshold_misspecified` on `discharge_pressure_com1`:

```
Historically typical operation (P25-P75 = 144.28–152.21) partially overlaps this
threshold — some normal operation sits outside the configured limit.
```

Most readings fall outside a configured limit, yet no protection setpoint was
breached and equipment health is normal. The platform's conclusion is that **the
limit is wrong, not the machine** — so it raises a configuration-review finding
at `info` severity and sends no alert.

This is the behaviour that distinguishes an engineering platform from a threshold
alarm. It is also the case that caught an earlier LLM regression: the model
described SC-126 as "not healthy" on the basis of mis-set thresholds. The system
prompt now carries an explicit never-escalate rule, and the evidence bundle
includes each finding's severity so the model cannot infer urgency that the
deterministic layer did not assert.

### Scenario 5 — ML finds something no rule covers

Isolation Forest reports novelty on SC-126:

```
Summary: Behaviour unlike history in 57 window(s) (hypothesis)
Detail:  Principal drivers: adu2_pressure (-2.50),
         cooling_water_pressure_inlet (+1.72),
         pressure_on_psa_2_tower (-1.45)
```

Every individual sensor is inside its limits — no rule fires. The *combination*
is unlike anything the machine has done before.

What the platform does **not** do: alarm. The finding is `origin = learned`,
`severity = info`, `status = hypothesis`, and it appears in the interface as an
"early signal", explicitly not a fault. Per-feature attribution is included so an
engineer can see *why* the model flagged it — the reason Isolation Forest was
chosen over an autoencoder, whose reconstruction error explains nothing.

### Scenario 6 — The learning loop closing

The step that makes the system improve with use.

1. An engineer opens the novelty finding and answers **"Was this worth flagging?"**
2. The verdict is stored, keyed on `identity_key`:

```
   identity   |   finding    |  unit  |      verdict       | author |    at
--------------+--------------+--------+--------------------+--------+----------
 570ffdfb43fc | 4efff651b2e1 | SC-126 | false_positive     | admin  | 09:12:44
 29c13e236b93 | 8a1c02be7791 | SC-126 | expected_behaviour | admin  | 09:12:47
```

3. The verdict is projected into the knowledge graph as its own node:

```
        node_id           |  standing  | author
--------------------------+------------+--------
 validation:570ffdfb43fc  | rejected   | admin
 validation:29c13e236b93  | explained  | admin
```

linked by `condition:… --validated_by--> validation:…`.

4. `GET /feedback/stats` reports label readiness honestly:

```json
{ "labelled_conditions": 2, "total_verdicts": 3, "target": 200,
  "percent_to_target": 1.0, "phase_c_ready": false }
```

**Why the verdict is keyed on `identity_key`, not `finding_id`.** A condition
receives a new `finding_id` on every observation. A verdict keyed to the
observation would be orphaned within 30 seconds. Keyed to the condition, the
label survives later observations and remains valid after the condition clears —
which is precisely the training example worth keeping.

---

## 5. Edge cases tested

Design decisions are only real if the failure they prevent is pinned by a test.

### 5.1 Escalation policy — 17 unit tests

| Case | Expected | Result |
|---|---|---|
| New critical condition | `triggered`, emailed | ✅ |
| Severity `warning` | no alert at all | ✅ |
| `warning` → `critical` | `triggered` | ✅ |
| Already critical before alerting existed | announced exactly once | ✅ |
| Re-trigger inside cooldown | recorded, `suppressed` | ✅ |
| Re-trigger after cooldown | emailed normally | ✅ |
| Resolution of a suppressed trigger | also suppressed | ✅ |
| Still critical past 30 min | `reminder` | ✅ |
| Still critical within 30 min | silent | ✅ |
| Reminders repeat | further reminders | ✅ |
| Severity drops from critical | `resolved` | ✅ |
| Condition disappears entirely | `resolved` | ✅ |
| Clears but was never announced | silent — no "resolved" for an unknown alarm | ✅ |
| Already resolved | not resolved twice | ✅ |
| Cascade of criticals | one alert per condition, one email | ✅ |
| Wording changes while critical | no re-trigger | ✅ |

### 5.2 Feedback loop — 28 end-to-end cases against the live stack

Run against real Postgres and the real HTTP API, not mocks.

**Authorisation and validation**

| Case | Expected | Result |
|---|---|---|
| Unauthenticated POST | `401` | ✅ |
| Unknown finding | `404` | ✅ |
| Verdict on a `derived` (measured) finding | `400` | ✅ |
| Verdict on a `diagnosed` finding | `400` | ✅ |
| Invalid verdict value | `422` | ✅ |
| Note longer than 2,000 characters | `422` | ✅ |

A measured threshold breach is not a prediction to confirm — "false positive" is
meaningless against a reading that genuinely crossed a setpoint. Only `learned`
findings accept a verdict.

**Recording semantics**

| Case | Expected | Result |
|---|---|---|
| First verdict | `201` | ✅ |
| Author taken from JWT, not request body | `admin` | ✅ |
| Same verdict clicked 4 times | **1 row** | ✅ |
| Changed verdict | 2 rows, audit trail kept | ✅ |
| Latest verdict wins | current = newest | ✅ |
| History endpoint | both verdicts returned | ✅ |

**Append-only enforcement (database level)**

| Case | Expected | Result |
|---|---|---|
| `UPDATE application.feedback` | rejected by trigger | ✅ |
| `DELETE FROM application.feedback` | rejected by trigger | ✅ |

**Persistence and the graph**

| Case | Expected | Result |
|---|---|---|
| Validation node created with standing | present | ✅ |
| `validated_by` edge created | present | ✅ |
| Graph records who judged it | `admin` | ✅ |
| **Verdict survives a live analysis run** | preserved | ✅ |
| Validation edge survives | preserved | ✅ |
| Labels not duplicated by the run | stable | ✅ |
| Label outlives the observation it was given on | preserved | ✅ |
| Stats count distinct conditions, not raw verdicts | 2 | ✅ |
| `phase_c_ready` honest | `false` | ✅ |

### 5.3 Regressions found and fixed during development

| Defect | Consequence | Fix |
|---|---|---|
| Findings re-recorded every cycle | 4,006 rows for 25 conditions | Material-change filter |
| Numbers embedded in prose | Filter never matched | Strip digits before comparing wording |
| Cleared conditions never disappeared | Stale conditions shown forever | `engine_run.observed_identities` |
| `GET /runs` returned 500 | Endpoint dead since D5 | Missing repository added to unit of work |
| nginx cached the API's IP | 502 after **every** redeploy | Runtime DNS resolution |
| Postgres refused to start after shutdown | Database unusable | Recreate directories the filesystem drops |
| Simulator ran a stale image | Alerting silently absent | `--build` on profile services |
| Circular import | Worked only by import order | Lazy import in the dispatcher |

### 5.4 The regression this architecture exists to prevent

The most important test in the suite, `test_validation_survives_a_pattern_reprojection`.

Graph node properties are **replaced wholesale** on upsert. The obvious way to
record an engineer's verdict — set `status = confirmed` on the pattern node —
would have been silently erased on the next Phase-B run. Labels would have rotted
invisibly, and the loss would only surface months later when the training set
turned out to be empty.

So a verdict is stored on **its own node**, linked by an edge that no other
projector touches. The test simulates a Phase-B re-projection overwriting the
condition node, then asserts the verdict is still present. It has an explicit
failure message: *"the engineer's verdict was erased by a model re-run."*

---

## 6. Transaction and failure boundaries

### 6.1 One transaction across two schemas

A single analysis cycle writes to: findings, the knowledge graph, alerts,
reports, model registry, and the engine-run record. **All of it commits or none
of it does**, inside one `AnalysisUnitOfWork` holding one session spanning both
`application` and `knowledge`.

The consequence is that the system cannot end up in a state where a finding
exists but its graph projection does not, or where an alert was decided but its
finding was rolled back.

### 6.2 Idempotency

`engine_run` carries `UNIQUE(unit, input_hash)`. A run begins with
`INSERT … ON CONFLICT DO NOTHING RETURNING`, so exactly one worker owns a given
input. Re-analysing the same data returns `replayed: true` and does nothing.

Verified with concurrent execution: five simultaneous analyses of one machine
produced one run record, one set of findings, and one projection.

### 6.3 What is deliberately outside the transaction

**Email dispatch.** Alert rows commit *with* the findings (the outbox pattern);
the email is sent *after* commit. This is deliberate:

- SMTP failure can never roll back an analysis.
- An alert can never be lost between "detected" and "emailed" — the row is
  already durable.
- Failed sends are retried on subsequent cycles, up to 5 attempts, then marked
  `failed` with the error preserved and visible.

**ML failures.** Pattern learning and forecasting are wrapped in exception
handlers. They are advisory hypotheses; if a model fails, the deterministic
analysis still completes. A model that cannot support a conclusion reports its
own reduced health rather than guessing.

---

## 7. Current state

| Metric | Value |
|---|---|
| Machines under continuous analysis | 6 |
| Sensor readings stored | 750,827 |
| Findings recorded | 8,503 |
| — measured (`derived`) | 7,663 |
| — rule-derived (`diagnosed`) | 723 |
| — ML hypotheses (`learned`) | 117 |
| Knowledge graph | 3,234 nodes / 3,649 edges |
| Analysis cycles completed | 6,660 |
| Escalation alerts | 39 |
| Automated tests | **231 passing** |
| Database migrations | 7 (`0001_baseline` … `0007_feedback`) |
| Analysis cadence | 30 seconds |
| Detection → email latency | ~2 seconds |

---

## 8. What is not built

Stated plainly, because a document that omits them is less useful.

**Phase C supervised models — not trained.** Failure probability and remaining
useful life require a labelled breakdown history the plant has not yet provided.
The interface shows a clearly-marked design preview so the target is reviewable,
but nothing computes those numbers. The feedback loop now generates labels for
*alarm quality*; true failure prediction still needs the maintenance register.

**Protocol ingestion — not built.** Data arrives by CSV and REST. OPC-UA and
Modbus adapters are required for direct PLC/SCADA connection.

**Maintenance and failure-mode graph nodes — not created.** The node types are
reserved in the schema (`FAULT_MECHANISM`, `FAILURE_MODE`, `MAINTENANCE_ACTION`)
but nothing populates them, for the same reason: no maintenance history has been
supplied.

**Before internet-facing deployment**, four items must be addressed: the JWT
secret and admin password are still development defaults; Python dependencies are
unpinned, which risks the reproducibility guarantee the platform rests on; and
CORS is unconfigured, which will break a split-origin deployment.

The single highest-value input the plant can provide is its **existing breakdown
register**. With historical failure dates it becomes possible to check
retrospectively whether the novelty and forecasting signals fired before known
failures — validating the models already running, without training anything.
