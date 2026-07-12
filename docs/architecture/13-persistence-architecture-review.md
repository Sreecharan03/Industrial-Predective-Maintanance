# ADR-019 — Production Persistence Architecture (Local Docker)

Status: **PROPOSED / REVIEW ONLY (2026-07-12)** — no code changed. Realizes the
persistence gaps from ADR-012-audit (KG persistence = Critical; DB abstraction =
partial) **without altering any business logic** (ADR-001…018 intact). Every new
artefact is an **infrastructure adapter behind an existing or additive port**.

## 0. Guiding rule — persistence lives *only* in the infrastructure ring

```
domain / findings / rules / pattern_learning / forecasting / engines   ← UNCHANGED
                    ▲ depend on ports (interfaces)
application (use-cases)  ─── depend on ───►  PORTS  ◄── implemented by ── infrastructure/*  (NEW)
                                              │                              │
                            TimeSeriesSource, KnowledgeGraphRepository,      │  PostgreSQL
                            ModelRegistry, FeedbackRepository, ArtifactStore │  + TimescaleDB
                            + additive: FindingRepository, ReportRepository, │
                              AssetRepository, UserRepository, RoleRepository,
                              RuleVersionRepository, AuditLogRepository, ConfigRepository
```

Not one line changes in engines/findings/rules/pattern_learning/forecasting. We
**add adapters** and, where a store has no port yet (findings, reports, users,
rules-as-data, audit, config), **add a new port interface** — the same pattern
already used for `TimeSeriesSource`/`KnowledgeGraphRepository`. Adding a port is
*extending* the architecture, never bypassing it.

---

## Deliverable 1 — Persistence Architecture Review

### 1.1 One Postgres instance, three logical schemas

A **single `timescale/timescaledb` Postgres instance** (TimescaleDB is a Postgres
extension) with **three schemas**, so cross-domain foreign keys are possible
where they add integrity, while the concerns stay cleanly separated:

| Schema | Purpose | Extension |
|---|---|---|
| `sensor_history` | operational time-series + engine-run history | **TimescaleDB hypertables** |
| `knowledge` | the Knowledge Graph (nodes/edges) | plain relational |
| `application` | assets, users/roles, findings, reports, registries, audit, config | plain relational |

### 1.2 Ports: reused vs. additive

| Store | Port | Status | Adapter (infra) |
|---|---|---|---|
| Sensor history read | `TimeSeriesSource` | **exists** | `DbTimeSeriesSource` (new) |
| Sensor history write | *new* `ReadingSink` | **additive** | `TimescaleReadingSink` |
| Knowledge Graph | `KnowledgeGraphRepository` | **exists** | `PostgresKnowledgeGraph` (new) |
| Model registry | `ModelRegistry` | **exists** | `PostgresModelRegistry` |
| Human feedback | `FeedbackRepository` | **exists** | `PostgresFeedbackRepository` |
| Artifacts | `ArtifactStore` | **exists** | keep `LocalArtifactStore` (blobs on volume) |
| Findings | *new* `FindingRepository` | **additive** | `PostgresFindingRepository` |
| Reports | *new* `ReportRepository` | **additive** | `PostgresReportRepository` |
| Assets/catalog | *new* `AssetRepository` | **additive** | `PostgresAssetRepository` (seeded from catalog) |
| Users/roles | *new* `UserRepository`,`RoleRepository` | **additive** | Postgres impls |
| Rule versions | *new* `RuleVersionRepository` | **additive** | `PostgresRuleVersionRepository` |
| Audit | *new* `AuditLogRepository` | **additive** | Postgres impl |
| Dynamic config | *new* `ConfigRepository` | **additive** | Postgres impl (static config stays in `Settings`) |

Existing `InMemory*` implementations are **retained** for tests — the port lets
unit tests stay DB-free while production wires the Postgres adapter.

### 1.3 The pandas boundary is preserved

`IngestedSeries` still carries a pandas frame. `DbTimeSeriesSource.load(unit)`
queries `sensor_reading`, **pivots long→wide** into the exact
`timestamp + sensor-key columns` frame the engines already consume, and returns
the *same* `IngestedSeries` dataclass. Engines never learn where the data came
from. CSV becomes a **bootstrap loader** that writes into `sensor_reading` via
`ReadingSink`; after bootstrap, every reader uses `DbTimeSeriesSource`.

---

## Deliverable 2 — Database ER Diagram

```
 ┌───────────────────────────  schema: application  ───────────────────────────┐
 │                                                                              │
 │  asset ──1:N── subsystem ──N:M── sensor      role ──N:M── user_account       │
 │    │              (subsystem_sensor)           (user_role)                   │
 │    │                                                                         │
 │    ├─1:N─ threshold (sensor_key)                                             │
 │    │                                                                         │
 │    ├─1:N─ finding ──1:N── finding_evidence                                   │
 │    │        │  (identity_key, finding_id, origin, category, severity,        │
 │    │        │   confidence, provenance, observed_window, source_engine)      │
 │    │        └─1:N── human_feedback (finding_identity_key)                    │
 │    │                                                                         │
 │    ├─1:N─ report (type, persona, window, status, artifact_id)                │
 │    ├─1:N─ rule_version (rule_id, version, definition JSONB, enabled)         │
 │    ├─1:N─ model_registry (model_id, version, seed, feature_schema, window)   │
 │    ├─1:N─ audit_log (actor, action, entity, entity_id, at, detail JSONB)     │
 │    └─1:N─ app_config (key, value JSONB, updated_by, updated_at)              │
 │                                                                              │
 └──────────────────────────────────────────────────────────────────────────────┘
        │ asset.key (FK, soft ref by unit text)                    │ artifact_id
        ▼                                                          ▼
 ┌────────────  schema: sensor_history  ────────────┐   ┌──── LocalArtifactStore ────┐
 │  sensor_reading  ⭐ HYPERTABLE                    │   │  <root>/<Type>/<id>.json    │
 │   (time, unit, sensor_key, value, quality, src)  │   └─────────────────────────────┘
 │  engine_run                                      │
 │   (run_id, unit, engine, version, input_hash,    │   ┌──────  schema: knowledge  ──────┐
 │    started_at, finished_at, status, artifact_id) │   │  kg_node (node_id, type, props) │
 │  ingest_watermark (unit, last_time)              │   │  kg_edge (src,dst,type, props)  │
 │  reading_hourly  (continuous aggregate)          │   │   FK src,dst → kg_node.node_id  │
 └──────────────────────────────────────────────────┘   └──────────────────────────────────┘
```

FKs within a schema are enforced; cross-schema links (`finding.unit → asset.key`,
`report.artifact_id`, `engine_run.artifact_id`) are **soft references by stable
text key** to avoid coupling the high-write time-series schema to app tables.

---

## Deliverable 3 — TimescaleDB Schema Design (`sensor_history`)

### 3.1 `sensor_reading` — the hypertable (narrow/long, Timescale-idiomatic)

```sql
CREATE TABLE sensor_history.sensor_reading (
    time       TIMESTAMPTZ      NOT NULL,
    unit       TEXT             NOT NULL,
    sensor_key TEXT             NOT NULL,
    value      DOUBLE PRECISION,
    quality    SMALLINT         NOT NULL DEFAULT 0,   -- 0=ok, >0 = quality flag
    source     TEXT             NOT NULL DEFAULT 'csv_bootstrap',
    PRIMARY KEY (unit, sensor_key, time)
);
SELECT create_hypertable('sensor_history.sensor_reading', 'time',
                         chunk_time_interval => INTERVAL '7 days');
CREATE INDEX ix_reading_unit_sensor_time
    ON sensor_history.sensor_reading (unit, sensor_key, time DESC);
```

**Why long, not wide:** sensor sets differ per unit and evolve; a narrow table
avoids schema churn, supports Timescale compression/continuous-aggregates
natively, and pivots cheaply to the engine frame. The reader pivots:

```sql
SELECT time, sensor_key, value FROM sensor_history.sensor_reading
WHERE unit = :unit AND time BETWEEN :start AND :end
ORDER BY time;   -- adapter pivots to wide IngestedSeries frame
```

### 3.2 Indexing, partitioning, compression, retention

- **Partitioning:** by `time`, 7-day chunks (tunable). Space-partition by `unit`
  only if a single unit's write rate demands it (not needed at 6 units).
- **Index:** `(unit, sensor_key, time DESC)` covers both the per-sensor forecast
  read and the "latest N" query.
- **Compression** (after 30 days) instead of dropping — the user explicitly needs
  history to **accumulate for future supervised ML**:
  ```sql
  ALTER TABLE sensor_history.sensor_reading SET (timescaledb.compress,
      timescaledb.compress_segmentby = 'unit, sensor_key');
  SELECT add_compression_policy('sensor_history.sensor_reading', INTERVAL '30 days');
  ```
- **Retention:** **raw data is NOT dropped** (needed for Phase C). Only a
  *documented* optional policy hook exists, disabled by default.
- **Continuous aggregate** for fast statistics/forecast reads:
  ```sql
  CREATE MATERIALIZED VIEW sensor_history.reading_hourly
  WITH (timescaledb.continuous) AS
  SELECT time_bucket('1 hour', time) AS bucket, unit, sensor_key,
         avg(value) avg_v, min(value) min_v, max(value) max_v, count(*) n
  FROM sensor_history.sensor_reading GROUP BY 1,2,3;
  SELECT add_continuous_aggregate_policy('sensor_history.reading_hourly',
      start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
      schedule_interval => INTERVAL '1 hour');
  ```
  Forecasting's hourly resample can read this directly — cheaper than raw scans.

### 3.3 `engine_run` — execution history

```sql
CREATE TABLE sensor_history.engine_run (
    run_id      UUID PRIMARY KEY,
    unit        TEXT NOT NULL,
    engine      TEXT NOT NULL,
    version     TEXT NOT NULL,
    input_hash  TEXT NOT NULL,
    window_start TIMESTAMPTZ, window_end TIMESTAMPTZ,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status      TEXT NOT NULL,          -- running|ok|failed
    artifact_id TEXT                    -- → ArtifactStore
);
```
Makes runs resumable/idempotent: `(engine, version, input_hash)` uniquely
identifies a computation, so a re-run is a no-op lookup (matches the platform's
deterministic-identity discipline).

---

## Deliverable 4 — Knowledge-Graph Persistence Design (`knowledge`)

`PostgresKnowledgeGraph` implements the **existing** `KnowledgeGraphRepository`
ABC verbatim — projector and every consumer are untouched.

```sql
CREATE TABLE knowledge.kg_node (
    node_id    TEXT PRIMARY KEY,
    node_type  TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_kg_node_type ON knowledge.kg_node (node_type);

CREATE TABLE knowledge.kg_edge (
    src        TEXT NOT NULL REFERENCES knowledge.kg_node(node_id) ON DELETE CASCADE,
    dst        TEXT NOT NULL REFERENCES knowledge.kg_node(node_id) ON DELETE CASCADE,
    edge_type  TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (src, dst, edge_type)          -- matches Edge identity (src,dst,type)
);
CREATE INDEX ix_kg_edge_type ON knowledge.kg_edge (edge_type);
CREATE INDEX ix_kg_edge_src  ON knowledge.kg_edge (src);
```

Port-method → SQL mapping (semantics identical to `InMemoryKnowledgeGraph`):

| Method | SQL |
|---|---|
| `upsert_node` | `INSERT … ON CONFLICT (node_id) DO UPDATE` (idempotent, matches projector) |
| `upsert_edge` | `INSERT … ON CONFLICT (src,dst,edge_type) DO UPDATE` |
| `get_node`/`has_node` | `SELECT … WHERE node_id=` |
| `nodes(type?)` | `SELECT … [WHERE node_type=] ORDER BY node_id` |
| `edges(type?,src?)` | filtered select, ordered |
| `neighbors(id,type?)` | `JOIN kg_edge ON src=id → kg_node` |
| `node_count`/`edge_count` | `SELECT count(*)` |

`Node.properties` / `Edge.properties` (already JSON-serialisable, telemetry-free
by ADR-014) map straight to `JSONB`. **No Neo4j** — the relational adapter fully
satisfies the current query surface; if graph-traversal queries later dominate,
Neo4j slots in behind the same port with zero consumer change.

---

## Deliverable 5 — Application Schema (`application`)

```sql
-- reference (seeded from senseminds.catalog; catalog stays source of truth)
asset(key PK, display_name, equipment_class, description)
subsystem(id PK, asset_key FK→asset, key, display_name)
sensor(id PK, key, source_column, display_name, sensor_type, unit_json JSONB)
subsystem_sensor(subsystem_id FK, sensor_id FK, PK(both))
threshold(id PK, asset_key FK, sensor_key, status, minimum, maximum, note)

-- reasoning outputs (produced by unchanged engines, persisted via new ports)
finding(finding_id PK, identity_key, unit FK→asset.key, finding_type, category,
        scope, origin, severity, confidence_value, confidence_rationale,
        summary, detail, target_key, subsystem_key, source_engine,
        observed_start, observed_end, input_hash, produced_at, supersedes)   -- immutable rows
finding_evidence(id PK, finding_id FK, artifact_id, description, observed_value_json)

-- identity/auth
user_account(id PK, username UNIQUE, email, hashed_password, is_active, created_at)
role(id PK, name UNIQUE, description)          -- operator, maint_eng, reliability, manager, exec, admin
user_role(user_id FK, role_id FK, PK(both))

-- registries / governance
rule_version(id PK, rule_id, version, definition JSONB, enabled, created_at,
             UNIQUE(rule_id, version))          -- rule DEFINITIONS as auditable data
model_registry(id PK, model_id, version, trained_at, window_start, window_end,
               feature_schema_version, seed, hyperparameters JSONB, artifact_id,
               UNIQUE(model_id, version))
human_feedback(id PK, finding_identity_key, verdict, author, note, created_at)

-- ops
report(id PK, type, persona, unit FK, window_start, window_end, status,
       requested_by FK→user_account, requested_at, artifact_id)
audit_log(id PK, actor, action, entity, entity_id, at TIMESTAMPTZ, detail JSONB)
app_config(key PK, value JSONB, updated_by, updated_at)
```

**No domain models are duplicated.** These tables are *persistence projections*
of existing Pydantic models; adapters map row↔model at the boundary
(`Finding`, `ModelMetadata`, `HumanFeedback`, `RuleDefinition`, `Asset`). Findings
are written **immutably** (new rows, `supersedes` pointer) — mirroring the
in-memory contract.

---

## Deliverable 6 — Migration Strategy

- **Tool:** **Alembic** (SQLAlchemy Core migrations) for `application` +
  `knowledge`; Timescale objects (`create_hypertable`, compression, continuous
  aggregates) issued as raw SQL **inside** Alembic revisions so the whole schema
  is one versioned, replayable history.
- **Revision ordering:** (1) extensions (`CREATE EXTENSION timescaledb`), (2)
  schemas, (3) `sensor_history` + hypertable, (4) `knowledge`, (5) `application`,
  (6) Timescale policies (compression/continuous-agg).
- **Seed (idempotent, repeatable):** reference data (`asset`/`subsystem`/
  `sensor`/`threshold`) seeded **from `senseminds.catalog`** so the catalog stays
  the source of truth and the DB is a projection; default `role`s; `rule_version`
  seeded from `senseminds.rules.catalog.DEFAULT_RULES`.
- **Bootstrap data migration:** a one-shot `csv_bootstrap` command reads the
  processed CSVs via the existing `ProcessedCsvSource` and writes into
  `sensor_reading` through `ReadingSink` with `ON CONFLICT (unit,sensor_key,time)
  DO NOTHING` — **idempotent**, safe to re-run.
- **Runs as a container job:** migrations execute in a dedicated `migrate`
  one-shot service that must succeed before `senseminds-api` starts (see Docker).
- **Forward-only** in production; destructive changes ship as expand→migrate→
  contract sequences.

---

## Deliverable 7 — Repository Interaction Diagram (transaction boundaries)

```
 CONTINUOUS INGESTION                    ANALYSIS PIPELINE (per unit run)
 ────────────────────                    ───────────────────────────────
 new reading(s)                          AnalysisUseCase.run(unit)
    │                                       │  ① OPEN read txn
    ▼                                       ▼
 ReadingSink.write_batch() ──┐           DbTimeSeriesSource.load(unit)  ← reading_hourly / raw
   ON CONFLICT DO NOTHING     │              │ (pivot → IngestedSeries)   ── close read txn
   (1 txn / batch, idempotent)│              ▼
    │                         │           engines/*.compute(...)         ← PURE, no DB
    ▼                         │           findings assembler / rules / patterns / forecasts
 sensor_reading (hypertable)  │              │
 ingest_watermark ◄───────────┘              ▼  ② OPEN write txn  (ONE atomic unit)
                                          ├─ FindingRepository.save_all(findings)
                                          ├─ KnowledgeGraphRepository.upsert_* (projector; idempotent)
                                          ├─ ArtifactStore.save(results)  (blob on volume)
                                          └─ engine_run.finish(status, artifact_id)
                                             ② COMMIT  → analysis durable-or-nothing
```

**Transaction rules:**
- **Ingestion:** one txn per batch; idempotent upsert ⇒ safe retry; advance
  `ingest_watermark` in the same txn.
- **Analysis:** reads and compute happen *outside* any long-held txn (engines are
  pure and touch no DB); **all persistence for one run commits in a single write
  transaction**, so a crash leaves the store either fully updated or untouched.
  KG upserts being idempotent makes a retried run safe.
- **API reads:** short read-only txns; no write path from query endpoints.
- **Unit of work:** one `SessionFactory`; use-cases receive repositories bound to
  one session so a use-case = one transaction.

---

## Deliverable — Docker Architecture (local production)

### Services

| Service | Image / build | Role | Profile |
|---|---|---|---|
| `postgres` | `timescale/timescaledb:latest-pg16` | sensor history + knowledge + application (one instance, 3 schemas) | default |
| `migrate` | app image, `alembic upgrade head` + seed + optional csv_bootstrap | one-shot, gates api | default |
| `senseminds-api` | app image, `uvicorn services.api:app` | REST API; **hosts the Postgres KG adapter in-process** | default |
| `ingestion-worker` | app image, ingestion loop | continuous reading persistence (recommended for the "accumulate over time" goal) | default |
| `pgadmin` | `dpage/pgadmin4` | DB inspection | `dev` only |

> The "Persistent Knowledge Graph adapter" is **not a separate container** — it is
> `PostgresKnowledgeGraph` running *inside* `senseminds-api` (and the worker),
> talking to the same `postgres`. Correct per Clean Architecture: it's a library
> adapter, not a service.

### compose shape

```yaml
services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment: [POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    networks: [smnet]
    healthcheck: {test: ["CMD-SHELL","pg_isready -U $$POSTGRES_USER"],
                  interval: 5s, timeout: 3s, retries: 10}
  migrate:
    build: .
    command: ["python","-m","senseminds.infrastructure.db.migrate"]
    environment: [SENSEMINDS_DB_URL, ...]
    depends_on: {postgres: {condition: service_healthy}}
    networks: [smnet]
    restart: "no"
  senseminds-api:
    build: .
    command: ["uvicorn","services.api.app:app","--host","0.0.0.0","--port","8000"]
    environment: [SENSEMINDS_DB_URL, SENSEMINDS_ARTIFACT_ROOT, SENSEMINDS_ENVIRONMENT, ...]
    volumes: ["artifacts:/data/artifacts"]
    depends_on: {postgres: {condition: service_healthy},
                 migrate:  {condition: service_completed_successfully}}
    ports: ["8000:8000"]
    healthcheck: {test: ["CMD","curl","-f","http://localhost:8000/ready"], ...}
    networks: [smnet]
  ingestion-worker:
    build: .
    command: ["python","-m","services.ingestion_worker"]
    depends_on: {postgres: {condition: service_healthy},
                 migrate:  {condition: service_completed_successfully}}
    networks: [smnet]
  pgadmin:
    image: dpage/pgadmin4
    profiles: ["dev"]
    depends_on: [postgres]
    ports: ["5050:80"]
    networks: [smnet]
volumes: {pgdata: {}, artifacts: {}}
networks: {smnet: {driver: bridge}}
```

- **Volumes:** `pgdata` (all three schemas — durable DB), `artifacts` (blob store
  for `LocalArtifactStore`). Both survive `compose down` (only `down -v` wipes).
- **Networking:** one private bridge `smnet`; only `senseminds-api` (8000) and
  `pgadmin` (5050, dev) publish ports; Postgres stays internal.
- **Env vars:** `SENSEMINDS_DB_URL` (async SQLAlchemy DSN), `POSTGRES_*` creds
  (from `.env`/secret, never committed), `SENSEMINDS_ARTIFACT_ROOT=/data/artifacts`,
  `SENSEMINDS_ENVIRONMENT=prod`, `SENSEMINDS_LOG_LEVEL`. `Settings` gains a
  validated `db_url` field (config-consistency preserved).
- **Startup sequence:** `postgres` (healthy) → `migrate` (runs to completion) →
  `senseminds-api` + `ingestion-worker` start. Health gates enforce order.
- **Health checks:** `pg_isready`; api `/ready` verifies DB connectivity +
  migration head (distinct from `/health` liveness).

**Explicitly excluded per constraints:** no Kubernetes, no cloud, no Redis, no
Kafka, no MQTT. Streaming ingestion adapters remain a future port behind
`TimeSeriesSource`/`ReadingSink`.

---

## Deliverable 8 — Implementation Roadmap

| Step | Scope | Exit criteria |
|---|---|---|
| **D0** | Add `db_url` to `Settings`; SQLAlchemy async engine + `SessionFactory` in `infrastructure/db/` | config validates; connects to Docker Postgres |
| **D1** | Alembic baseline: extensions, schemas, `application` tables | `alembic upgrade head` clean; seed reference data from catalog |
| **D2** | `sensor_history` hypertable + `ReadingSink` + `DbTimeSeriesSource` + `csv_bootstrap` | CSV → DB; engines run off `DbTimeSeriesSource`, **parity tests still green** |
| **D3** | `PostgresKnowledgeGraph` behind existing ABC | KG idempotency tests pass against Postgres; restart-durable |
| **D4** | New ports + adapters: `FindingRepository`, `ModelRegistry`, `FeedbackRepository`, `ReportRepository`, `RuleVersionRepository`, `AuditLogRepository` | round-trip tests; findings/models/feedback persist |
| **D5** | `AnalysisUseCase` unit-of-work (single write txn) + `engine_run` history | crash-atomic run; idempotent re-run is a no-op |
| **D6** | `ingestion-worker` continuous loop + watermarks | new readings accumulate; forecasting/pattern reads from DB, never CSV |
| **D7** | Docker compose (postgres, migrate, api, worker, pgadmin-dev) + healthchecks | `docker compose up` yields a working local stack |
| **D8** | Continuous aggregate + compression policies; integration tests | hourly reads served from CAGG; 30-day compression active |

**Timescale/compression policies land in D8, after correctness (D2–D6) is
proven** — performance tuning never precedes parity.

---

## Constraints check (self-audit)

- ✅ No deterministic analytics rewritten — engines untouched; only their *data
  source* changes behind `TimeSeriesSource`.
- ✅ Findings / Rule Engine / Pattern Learning / Forecasting unchanged — they gain
  **persistence via new ports**, not modified logic.
- ✅ Repository abstractions honoured — KG uses the **existing** ABC; new stores get
  **new ports**, impls confined to `infrastructure/`.
- ✅ No domain models duplicated — tables are projections; adapters map at the edge.
- ✅ Clean Architecture intact — all persistence in the outer ring; dependencies
  point inward only.
- ✅ No Neo4j / K8s / cloud / Redis / Kafka / MQTT.

**No code changed. Awaiting approval** to begin at **D0**, then proceed step-by-
step (stopping after each, per standing cadence). Recommended first: **D0–D2**
(prove the sensor-history round-trip keeps every parity test green) before
touching KG and the new application ports.

---

## 14. Accepted refinements (owner, 2026-07-12) — D0–D2 authorized

ADR-019 approved with four refinements; **D0–D2 only** authorized after they are
incorporated. Stop after D2 with an implementation summary before KG persistence.

**R1 — Repository boundaries aligned to aggregate roots, not tables.** Repositories
are defined per *aggregate*, not per table, to keep the port layer cohesive:
- `AssetRepository` owns the **asset aggregate** — assets, subsystems, sensors,
  **and thresholds** (one root; sensors/subsystems/thresholds are not separate
  ports).
- `UserRepository` owns the **identity aggregate** — users **and their roles**
  (no standalone `RoleRepository`).
- `FindingRepository` owns findings **and their evidence** (evidence rows are part
  of the finding aggregate, never a separate port).
- Registries stay as their existing single-aggregate ports (`ModelRegistry`,
  `FeedbackRepository`), plus `ReportRepository`, `RuleVersionRepository`,
  `AuditLogRepository`, `ConfigRepository`. **No repository is created merely
  because a table exists.** (Supersedes the per-store port table in §1.2 — the
  tables are unchanged; only how ports group them changes.)

**R2 — `engine_run` moves `sensor_history` → `application`.** Engine-execution
history is application execution *metadata*, not operational sensor history. It
sits in the `application` schema beside `audit_log`, `report`, `model_registry`,
and `rule_version`. `sensor_history` now holds **only** true operational data
(`sensor_reading` hypertable, `ingest_watermark`, and the continuous aggregate).

**R3 — `ReadingValidation` stage before `ReadingSink`.** A lightweight, pure
validation stage sits between ingestion and persistence; the DB only ever
receives validated industrial readings. It checks, per reading:
- **timestamp integrity** (parseable, not null, within sane bounds),
- **duplicate detection** (same `(unit, sensor_key, time)` within the batch),
- **quality flags** (carried through / defaulted),
- **unit consistency** (reading's unit matches the ingest target),
- **missing fields** (unit/sensor_key/time present),
- **obviously invalid values** (non-finite: NaN/±inf rejected or flagged).
It yields accepted readings + a rejection report (reason per dropped reading) for
observability. It is pure (no I/O), unit-testable, and independent of the sink.
The `ReadingSink` then persists only accepted readings (`ON CONFLICT DO NOTHING`).

**R4 — Schema independence for future physical split.** The three schemas stay
loosely coupled enough to become **independent databases** later without touching
domain/application layers:
- **No cross-schema foreign keys.** Links across schemas are **soft references by
  stable text key** (`finding.unit`, `report.artifact_id`, `engine_run.unit`);
  FKs are used **only within** a schema. (Confirms the §1.1 stance and makes it a
  hard rule.)
- **Per-schema session/connection seam.** The DB layer exposes a
  `SessionFactory` **per logical store** (sensor-history / knowledge /
  application) resolved from config, so pointing one schema at a different DB URL
  later is a config change, not a code change. For the current local deployment
  all three resolve to the **same** Postgres instance/URL.
- **No transaction spans two schemas.** A unit of work commits within a single
  schema; cross-store consistency is handled by idempotent re-projection
  (already the platform's model), never a distributed transaction.

**Success criteria for D0–D2 (unchanged):** engines consume data exclusively via
`DbTimeSeriesSource`; CSV is bootstrap-only; history accumulates continuously in
TimescaleDB; **all existing parity tests remain byte-identical** after the
storage transition.
