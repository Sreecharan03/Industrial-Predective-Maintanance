# SenseMinds 360 — Production Readiness Review (ADR-001…018 complete)

Status: **REVIEW ONLY (2026-07-12)** — no code changed.审计 covers the whole
repository as implemented: 13 packages, **6,529 src LOC**, **2,610 test LOC**,
**158 test functions**, 18 accepted ADRs. Findings are categorized
Critical / High / Medium / Low. Nothing was modified silently.

---

## Phase 1 — Architecture Audit

### 1.1 Dependency direction & layering (measured)

The internal import graph (extracted from source):

```
domain            -> (nothing)                              ✅ innermost, zero deps
config            -> (nothing)                              ✅
infrastructure    -> domain                                 ✅
ingestion         -> catalog, domain, infrastructure        ✅
catalog           -> domain, infrastructure                 ✅
engines           -> domain, ingestion, catalog, infra, **application**  ⚠️
findings          -> domain, engines                         ✅ (reads result models)
knowledge_graph   -> domain, findings, catalog               ✅
rules             -> domain, findings                         ✅
pattern_learning  -> domain, findings, ingestion, knowledge_graph  ✅
forecasting       -> domain, findings, ingestion, catalog, pattern_learning  ✅
application       -> engines, ingestion                       ✅ (orchestrator, outer)
interfaces        -> config, infrastructure                   ✅
```

`domain` correctly depends on nothing; the dependency rule (inward) holds
**everywhere except one edge**, detailed below.

### 1.2 Findings

| # | Severity | Area | Finding |
|---|---|---|---|
| A1 | **High** | Layer violation / latent cycle | `engines/health/engine.py` imports `application.context.AnalysisContext`. The Health engine (analytics ring) depends **upward** on the orchestration ring. `application.context` in turn imports seven engine result types. No runtime cycle *today* (context does not import `HealthResult`), but it is a **latent circular dependency**: the moment the context needs to carry a HealthResult, the cycle closes. Root cause: Health is not really a leaf engine — it is a **fan-in composed analysis** over other engines' results, so it belongs at the application/composition layer, not under `engines/`. |
| A2 | Medium | Exception hierarchy | Error types are fragmented with **no shared platform base**: `EngineError`/`EngineInputError` (engines), `MissingDependencyError(RuntimeError)` (application), `ArtifactNotFoundError(KeyError)` (infra), raw `ValueError` (artifact-store id validation). A single `SenseMindsError` root with subtrees would let the API map errors to HTTP codes uniformly. |
| A3 | Medium | Interface consistency | Engine entrypoints are heterogeneous: `compute(series)`, `compute(context)`, `evaluate(series)`, `forecast_unit(...)`, `evaluate(findings, context)`, `project(...)`, `select(...)`. `BaseEngine` supplies `provenance`/`log` but **no abstract entrypoint**, so there is no enforced contract. Inputs genuinely differ, but a small typed `Protocol` family (Analyzer / Reasoner / Learner) would make orchestration and testing uniform. |
| A4 | Medium | Test coverage measurement | No coverage tooling is configured (no `pytest-cov`, no gate). 158 tests with a strong parity suite, but forecasting / rules / pattern_learning are referenced in only 1–2 test files each vs. 20 for engines. Coverage is likely good but **unmeasured**, so gaps are invisible. |
| A5 | Low | Naming consistency | Result classes are consistent (`<X>Result`); engine method names are not (see A3). Package naming is clean and consistent. |
| A6 | Low | Documentation | ADRs are excellent and internally consistent. Missing: a top-level repo `README`, per-package docstring index, and generated API docs. |
| — | ✅ | Circular dependencies | None at runtime (verified). Only the A1 latent risk. |
| — | ✅ | Duplicate logic | None material. Forecasting **reuses** `PatternResult`/`ModelHealth` from pattern_learning (deliberate, documented) — reuse, not duplication. |
| — | ✅ | Dead code / unused abstractions | None found. Ports (`ArtifactStore`, `KnowledgeGraphRepository`, `ForecastModel`, `PatternModel`, `FeedbackRepository`, `LanguageModel`-to-come) each have ≥1 consumer. |
| — | ✅ | Artifact management | `LocalArtifactStore` does **atomic writes** (temp+rename), **path-traversal-guards** artifact ids, and `result_type` round-trips safely (save & load both resolve to the class name — verified, no bug). |
| — | ✅ | Logging strategy | Single-line structured **JSON** logging, configured once, context-binding adapters. Production-grade. |
| — | ✅ | Config consistency | One `Settings` (pydantic-settings), env-prefixed, **fail-fast** validation, cached. |

**Phase 1 verdict:** architecturally sound. **One High** (A1) is the only true
violation and has a clean, contained fix (relocate Health to the composition
layer). Everything else is Medium/Low hardening.

---

## Phase 2 — Production Readiness Review

Evaluated as if deploying inside a Laurus Labs plant. **✅ = present/adequate,
⚠️ = partial, ❌ = absent (expected pre-production gap).**

| Concern | State | Notes |
|---|---|---|
| Configuration management | ✅ | 12-factor, validated, fail-fast. |
| Secrets | ❌ | `.env` only; no secret backend (Vault/SM/K8s secrets), no separation of secret vs. config. |
| Environment handling | ✅ | `environment` ∈ {local,dev,staging,prod}, validated. |
| Logging | ✅ | Structured JSON. |
| Observability / Metrics / Tracing | ❌ | No `/metrics` (Prometheus), no OpenTelemetry spans, no health of *engines* (only app liveness). |
| Performance / Memory | ⚠️ | pandas in-memory **per unit** — fine for 6 units of historical data; no chunking/streaming for large windows. |
| Streaming readiness | ❌ | Batch/CSV only. A real plant emits live OPC-UA / MQTT / historian streams. **The ports design supports adding a streaming `DataSource`** without touching engines — foundation is right, adapter is missing. |
| Scalability | ⚠️ | Engines are **stateless & pure** (horizontally scalable behind a queue); blocked only by in-memory KG (below). |
| Thread safety | ⚠️ | `get_settings` (lru_cache) and idempotent projections are safe; `InMemoryKnowledgeGraph` and the `_CONFIGURED` logging flag are **not** concurrency-hardened. |
| Fault tolerance / Recovery | ❌ | No ret/idempotent job runner, no checkpointing. Idempotent projections + immutable artifacts are a **strong recovery foundation**, not yet wired into a resumable pipeline. |
| Artifact retention | ❌ | No GC/TTL/retention policy; artifacts accumulate unbounded. |
| Model versioning | ✅ | `ModelRegistry` (id, version, trained_at, window, seed, hyperparams). |
| Rule versioning | ⚠️ | Rule definitions carry versions; **no persistent, auditable rule-version store** (rules are code-defined today). |
| Knowledge Graph persistence | **❌ Critical** | **In-memory only.** All learned knowledge is lost on restart. The `KnowledgeGraphRepository` ABC exists (clean seam), but the sole impl is `InMemoryKnowledgeGraph`. This is the #1 production blocker. |
| Database abstraction | ⚠️ | Ports exist (`ArtifactStore`, `KnowledgeGraphRepository`); only local/in-memory impls. No relational store for assets/runs/audit. |
| API boundaries | ❌ | Only `GET /health`. The ADR-018 API surface is unbuilt (expected — Phase 4). |
| Security / AuthN / AuthZ | ❌ | None. |
| Rate limiting | ❌ | None. |
| Input validation | ✅ | Pydantic v2 `frozen`/`extra=forbid` throughout; artifact-id sanitization. |
| Deployment / Docker | ❌ | No Dockerfile / compose / manifests. |
| CI/CD | ❌ | No pipeline (ruff+pytest run locally only). |
| Testing strategy | ⚠️ | Excellent unit + **parity** tests; no integration/e2e/load tests, no coverage gate. |
| Disaster recovery | ❌ | No backup/restore story (follows from KG/artifact persistence gaps). |

**Phase 2 verdict:** the **core intelligence is production-quality**; the
**operational shell is not built yet** — which is exactly the expected state
entering an integration phase. The single Critical is **KG persistence**; the
rest cluster into "operational hardening" work packages.

---

## Phase 3 — Recommended Production Repository Structure

The current layout is already Clean-Architecture-compliant. Recommended final
shape (maps the requested folders onto the existing rings; **⟵ = already exists**):

```
senseminds360/
├── senseminds/                     # the library (pure, deployable-agnostic)
│   ├── domain/            ⟵        # entities, value objects, enums  (Ring 0)
│   ├── shared/                     # NEW: cross-cutting contracts & errors
│   │   ├── errors.py               #   SenseMindsError root hierarchy (fixes A2)
│   │   └── protocols.py            #   Analyzer/Reasoner/Learner (fixes A3)
│   ├── config/           ⟵        # Settings  (Ring 0/infra-config)
│   ├── engines/          ⟵        # deterministic analytics  (Ring 1)
│   ├── findings/         ⟵        # finding contract  (Ring 1)
│   ├── graph/            ⟵ (knowledge_graph)  # KG models + repository port
│   ├── rules/            ⟵        # rule engine  (Ring 1)
│   ├── pattern_learning/ ⟵        # Phase B unsupervised  (Ring 1)
│   ├── forecasting/      ⟵        # Phase B forecasting  (Ring 1)
│   ├── llm/                        # NEW (ADR-018): grounded communication
│   ├── application/      ⟵        # use-cases, pipeline, AnalysisContext, Health (Ring 2)
│   └── infrastructure/   ⟵        # artifact store, logging, + persistence adapters
│       ├── artifact_store/  ⟵
│       ├── graph_store/            # NEW: persistent KG adapter (fixes Critical)
│       ├── db/                     # NEW: relational adapter (assets/runs/audit)
│       └── logging.py    ⟵
├── services/                       # NEW: long-running deployables (Ring 3)
│   ├── api/                        #   FastAPI app  (moves interfaces/api.py here)
│   ├── ingestion_worker/           #   batch + (future) streaming intake
│   └── report_service/             #   scheduled report generation
├── api/                            # OpenAPI schema, request/response DTOs (versioned)
├── dashboard/                      # NEW: frontend (separate build, consumes API)
├── deployment/                     # NEW: Dockerfiles, compose, k8s, CI config
├── examples/                       # NEW: runnable demos (SC-126 walkthrough)
├── tests/                ⟵        # unit + parity + (new) integration/e2e
└── docs/                 ⟵        # ADRs + this review
```

**Clean-Architecture checks:** `services/*` and `api/*` (Ring 3) may import
`application` (Ring 2), which imports Rings 0–1; nothing inner imports outward.
Relocating **Health → application** and **api → services/api** removes the only
inward-pointing violation. `llm/` sits at Ring 1/2 boundary (consumes findings/
graph/forecasts, produces no engine facts) — consistent with ADR-018.

---

## Phase 4 — Production REST API (design review, no implementation)

Base: `/api/v1` (URI **versioning**; `Accept` header negotiation reserved for
v2). JSON. **Cursor pagination** (`?cursor=&limit=`, opaque cursor) for all
collections. **AuthN**: OIDC/JWT bearer. **AuthZ**: role scopes (Phase 5
personas). Rate limiting per API key/role. All inputs Pydantic-validated;
errors follow the `SenseMindsError→HTTP` map (A2).

| Group | Endpoints (representative) | Notes |
|---|---|---|
| Health / Ops | `GET /health` ⟵, `GET /ready`, `GET /metrics` | liveness vs. readiness split; Prometheus. |
| Assets | `GET /assets`, `GET /assets/{unit}`, `GET /assets/{unit}/subsystems` | from catalog. |
| Sensors | `GET /assets/{unit}/sensors`, `GET /assets/{unit}/sensors/{key}` | definitions + thresholds; **raw telemetry only via** `?include=series` explicit flag. |
| Findings | `GET /findings?unit=&origin=&category=&severity=&since=` | filter by DERIVED/DIAGNOSED/LEARNED; cursor-paginated. |
| Diagnoses | `GET /diagnoses?unit=`, `GET /diagnoses/{finding_id}` | fired rules + antecedent chain. |
| Forecasts | `GET /forecasts?unit=&sensor=` | hypotheses + interval + backtest coverage. |
| Patterns | `GET /patterns?unit=&kind=` | novelty/regime hypotheses + model health. |
| Knowledge Graph | `GET /graph/nodes`, `GET /graph/edges`, `GET /graph/subgraph?unit=&depth=` | read-only projection. |
| Reports | `POST /reports {type, unit, window, persona}` → `GET /reports/{id}` | six ADR-018 report types; async job + artifact id. |
| LLM Query | `POST /llm/query {question, persona, unit}` | grounded answer + citations; **SSE token streaming** at `text/event-stream`. |
| Administration | `POST /runs` (trigger analysis), `GET /runs/{id}`, `GET /models`, `GET /rules` | run orchestration, model/rule registries. |
| Auth | `POST /auth/token`, `GET /auth/me` | OIDC exchange. |

**Streaming**: SSE for LLM tokens and live finding feeds; WebSocket reserved for
future real-time telemetry dashboards. **Every engineering response echoes the
citing ids** (ADR-018) so the API is auditable, not just the LLM.

---

## Phase 5 — Dashboard Architecture (design review, no frontend)

A separate SPA consuming **only** `/api/v1` (never the engines directly). All
views render **grounded evidence with citations**; facts vs. hypotheses are
visually distinct (ADR-018 §3/§5). Role-based composition, not separate apps.

| View | Purpose | Primary API |
|---|---|---|
| Asset Overview | Fleet health tiles (6 units), severity roll-up, open hypotheses | `/assets`, `/findings` |
| Machine Detail | One unit: subsystems, active findings, diagnoses, forecasts | `/assets/{unit}`, `/diagnoses` |
| Sensor Detail | One sensor: thresholds, stats, forecast band; telemetry chart **on demand** | `/sensors/{key}` (+`?include=series`) |
| Timeline | Operating-state episodes + findings over time | `/patterns`, `/findings?since=` |
| Knowledge Graph | Interactive condition/diagnosis/hypothesis graph | `/graph/subgraph` |
| Diagnosis View | A diagnosis + its fired rule + antecedent evidence chain | `/diagnoses/{id}` |
| Forecast View | Approach hypotheses, lead time, intervals, backtest coverage | `/forecasts` |
| Reports | Generate/read the six report types per persona | `/reports` |
| Investigation Mode | Free traversal: pivot facts→rules→hypotheses→artifacts | `/graph`, `/findings`, `/diagnoses` |
| LLM Assistant | NL Q&A with streamed, cited answers | `/llm/query` (SSE) |

**Role-based dashboards** (default landing + visible widgets): Operator →
Overview+Timeline; Maintenance Engineer → Machine Detail+Diagnosis+Reports;
Reliability Engineer → all + Investigation; Plant Manager → Overview+Forecast+
Executive report; Executive → roll-up only. Same evidence, different composition
(mirrors ADR-018 §9 persona-invariance).

---

## Phase 6 — Final Gap Analysis

### Required for MVP (must exist to run in a plant)
1. **KG persistence** (Critical) — a durable `KnowledgeGraphRepository` adapter.
2. **Relational store** for assets/runs/findings index + audit trail.
3. **REST API** (Phase 4 core: assets, findings, diagnoses, forecasts, reports, health).
4. **AuthN/AuthZ** (OIDC + role scopes) and **input validation at the edge**.
5. **LLM layer implementation** (ADR-018 scope) — the platform's stated interface.
6. **Deployment**: Dockerfile(s) + compose, **CI** (ruff+pytest+coverage gate).
7. **Fix A1** (relocate Health) — do this *before* building services on top.
8. **Secrets handling** (env→secret backend seam).
9. **Basic observability**: `/metrics`, `/ready`, structured request logging.

### Recommended (hardening before scale)
- Streaming `DataSource` adapter (OPC-UA/MQTT/historian) behind existing ports.
- OpenTelemetry tracing; per-engine health/metrics.
- Artifact & KG **retention/GC** policy; backup/restore (DR).
- Resumable, idempotent **pipeline job runner** with checkpointing.
- `SenseMindsError` root hierarchy (A2) + typed engine `Protocol`s (A3).
- Integration/e2e/load test tiers; coverage measurement (A4).
- Rate limiting, request quotas per role.
- Persistent, auditable **rule-version store**.

### Future roadmap (deliberately deferred)
- **Phase C supervised learning** (needs labeled maintenance events).
- Multi-plant / multi-tenant; cross-asset (multivariate) forecasting.
- Deep forecast models (only if a backtest earns them — ADR-017).
- Real-time streaming analytics (vs. batch) end-to-end.
- Mobile/field client; alerting/notification integrations.

### Explicitly **not** recommended (avoid scope creep)
Auto-remediation/actuation, autonomous rule creation, RUL without labels,
generic "AI insights" beyond the grounded evidence model.

---

## Deliverable 7 — Updated Roadmap

| Stage | Scope | Exit criteria |
|---|---|---|
| **P0 — Foundation fix** | A1 (Health→application), A2 error root, A3 protocols, `pytest-cov` gate | green suite, no inward violation, coverage baseline |
| **P1 — Persistence** | KG persistent adapter + relational store behind existing ports; retention policy | restart-durable knowledge; DR backup/restore |
| **P2 — Serving** | ADR-018 **LLM layer** + core **REST API** (Phase 4) + AuthN/AuthZ | grounding/citation/hallucination tests pass; secured endpoints |
| **P3 — Operability** | Docker/compose, CI/CD, `/metrics`+`/ready`, OTel tracing, secrets backend | reproducible deploy; observable in a dashboard |
| **P4 — Dashboard** | Frontend (Phase 5 views), role-based | operator→executive journeys working end-to-end |
| **P5 — Streaming** | live `DataSource` adapter, resumable pipeline | near-real-time ingestion without engine changes |
| **Phase C (later)** | supervised learning | once labeled maintenance data exists |

---

## Summary

- **Architecture: sound.** One High violation (A1), no runtime cycles, clean
  ring structure, real ports, strong immutability/provenance/parity discipline.
- **Production shell: not yet built** — as expected entering integration. One
  **Critical** blocker (KG persistence); the rest is well-scoped hardening.
- **Recommended first move:** **P0 foundation fix** (A1 relocation + error/
  protocol/coverage hygiene) *before* stacking services — cheapest now, costly
  later.

**No code changed. Awaiting approval** on: (a) accepting these severities, and
(b) which stage to authorize first (recommended: P0, then P1/P2).
