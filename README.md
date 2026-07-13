# SenseMinds 360 — Industrial Intelligence Platform

An explainable, grounded industrial-intelligence platform for pharmaceutical
refrigeration and utility equipment (screw compressors, air and nitrogen plants).
It turns raw sensor history into **deterministic engineering findings**, a
**knowledge graph**, **rule-based diagnoses**, **learned hypotheses and
forecasts**, and finally a **grounded, citation-enforced LLM** that explains all
of it in plain language — without inventing anything.

Built and validated on **6 real machines** at Laurus Labs (Visakhapatnam):
`SC-126`, `SC-114`, `SC-104`, `COM-102`, `COM-110`, `COM103 & NP102`
(≈ **2.86 million sensor readings**).

---

## The core idea

Most "AI for maintenance" tools jump straight to black-box ML. SenseMinds inverts
that: **deterministic engineering first, learning second, language last.** Every
layer is explainable, reproducible, and can be traced back to the exact data and
rule that produced it. The LLM is a *narrator over grounded evidence*, never a
source of truth — and it is architecturally prevented from hallucinating.

```
Sensor history (TimescaleDB)
      │
      ▼
Deterministic analytics (7 engines: statistics, thresholds, operating-state,
      │                   envelope, timeline, reliability, health)
      ▼
Engineering Findings  ──►  Knowledge Graph  ──►  Rule Engine (diagnoses)
      │                                              │
      ├──► Pattern Learning (unsupervised novelty / regimes)   [Phase B]
      ├──► Forecasting (short-horizon, backtested)             [Phase B]
      ▼
Grounded LLM communication layer (cited, register-aware)  ──►  REST API / Dashboard
```

Design is captured in **19 Architecture Decision Records** under
[`docs/architecture/`](docs/architecture/) (ADR-001 … ADR-019).

---

## What it can do today (all validated end-to-end from Docker Compose)

1. **Ingest** sensor data continuously into TimescaleDB (CSV bootstrap now; live
   OPC-UA / MQTT is a future adapter behind the same interface).
2. **Automatically run** the full analysis pipeline for an asset.
3. **Persist** every output atomically — findings, knowledge graph, reports,
   engine-run audit, artifacts — all commit or all roll back.
4. **Answer natural-language questions** through the grounded LLM (Groq
   Llama-3.3-70B, or an offline deterministic stub) — every engineering claim
   cites a real finding id; unsupported claims are dropped.
5. **Expose REST APIs** (JWT auth + roles).
6. **Serve dashboard data** (assets, findings, diagnoses, forecasts, KG subgraph,
   reports).
7. **Generate reports** (daily asset-health, etc.).
8. **Run entirely from `docker compose up`.**

---

## Project status — stage completion

> Honest, component-level percentages. "Frozen" = complete, reviewed, and not to
> be changed unless a defect is found.

| Layer / component | Status | % |
|---|---|---|
| **Architecture & ADRs** (001–019) | Complete, accepted | **100%** 🔒 |
| **Deterministic engines** (7) | Complete, parity-tested vs Phase-1 | **100%** 🔒 |
| **Findings layer** (immutable contract) | Complete | **100%** 🔒 |
| **Knowledge Graph** (+ persistence, restart-durable) | Complete | **100%** 🔒 |
| **Rule Engine** (diagnoses, auditable reasoning) | Complete | **100%** 🔒 |
| **Persistence** (TimescaleDB + repos + UnitOfWork) | Complete, byte-parity proven | **100%** 🔒 |
| **Analysis orchestration** (atomic, idempotent, concurrent-safe) | Complete | **100%** 🔒 |
| **Pattern Learning** (unsupervised novelty / regimes) | Implemented; not yet wired into live pipeline | **90%** |
| **Forecasting** (short-horizon, backtested) | Implemented; not yet wired into live pipeline | **90%** |
| **LLM communication layer** (ADR-018, grounded + cited) | Complete; live Groq validated | **100%** |
| **REST API** (assets/findings/diagnoses/reports/graph/analyze/llm) | Core complete | **90%** |
| **Auth** (JWT + roles + seed) | Working; no OIDC/refresh/user-mgmt UI | **80%** |
| **Ingestion worker** (idempotent analysis cycles) | Batch cycles work; live streaming deferred | **85%** |
| **Docker / deployment** (compose stack) | Runs end-to-end; needs dep pinning + hardening | **90%** |
| **Monitoring / logging** (JSON logs, `/metrics`, `/ready`) | Basic done; no OpenTelemetry tracing yet | **60%** |
| **Dashboard** (React SPA — overview, fleets, asset detail, findings, reports, Copilot) | Built, runs in the stack | **90%** |
| **Phase C — supervised learning** | Deferred (needs labeled maintenance events) | **0%** |
| **Testing** | 226 tests (unit + parity + integration) | **90%** |

**Overall platform: ~90% of a production-style MVP.**
The intelligence core, serving layer and dashboard are done; the main remaining
work is wiring pattern-learning/forecasting into the live run, dependency
pinning, and (future) streaming + supervised learning.

### Dashboard

A light, warm React SPA (`frontend/`) — deliberately **not** the usual dark-navy
"AI" look. The palette is **computationally validated**, not eyeballed: every hue
passes a lightness band, chroma floor, contrast (≥3:1 on the light surface) and
colour-vision-deficiency separation check (adjacent ΔE2000 ≥ 12 under protan /
deutan / tritan simulation).

- **Categorical** (chart series, fixed order): `#7C3AED` violet · `#0F9D8F` teal ·
  `#C026D3` fuchsia · `#4D7C0F` olive · `#0284C7` cyan
- **Status** (reserved, always with an icon + label — never colour alone):
  `#15803D` healthy · `#57534E` info · `#B45309` watch · `#BE123C` critical

Pages: **Overview** (plant health, fleet, what needs a look) · **Refrigeration /
Air Compressors / Nitrogen Plant** fleets · **Asset detail** (findings, sensors,
knowledge graph, reports, run history, one-click analysis) · **Findings** ·
**Reports** · **Plant Copilot** (grounded chat — every claim shows its cited
finding ids, and gaps appear as *insufficient evidence*).

It shows only what the platform actually computes — **no invented failure
probability or RUL**, because the backend does not produce them yet.

### Test suite
- **226 passing** with a database (unit + parity + integration).
- **195 passing / 31 skipped** offline (integration tests skip gracefully with no DB).
- `ruff` clean. Deterministic engine outputs are **byte-identical** whether data
  is loaded from CSV or reconstructed from TimescaleDB (proven for all 6 machines).

---

## Key engineering findings (what the platform actually concluded)

The platform is honest — it does **not** invent problems:

- **SC-126 is a healthy, stable baseload machine.** Its "threshold" findings are
  **mis-specified operating limits (a configuration/data issue), not equipment
  faults** — the supplied limits don't match how the machine actually runs. The
  grounded LLM correctly reports this as *"mis-set operating limits rather than
  faults"* and refuses to escalate it into a health problem.
- Several sensors show **drift between the first and second half of history** and
  **flatlined (repeated-identical) readings** — data-quality / reliability
  signals, surfaced as findings, not alarms.
- With no forecast evidence present, the LLM **refuses to claim** any limit is
  "being approached soon" and lists that gap under *insufficient evidence* — the
  anti-hallucination design working as intended.

---

## Run it

```bash
cd deployment
cp .env.example .env          # set POSTGRES_PASSWORD, JWT secret, admin password
                              # optional: SENSEMINDS_GROQ_API_KEY (empty => offline stub)
docker compose up --build     # postgres+timescale, migrate, api, worker, dashboard
```

* **Dashboard → http://localhost:3000** (sign in with the admin credentials from `.env`)
* API → http://localhost:8000

Then:

```bash
# health
curl localhost:8000/health

# login (default admin/admin — change in .env)
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/token \
  -d "username=admin&password=admin" | jq -r .access_token)

# run analysis + read results
curl -X POST localhost:8000/api/v1/analyze -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"unit":"SC-126"}'
curl localhost:8000/api/v1/assets/SC-126/findings -H "Authorization: Bearer $TOKEN"

# ask the grounded LLM
curl -X POST localhost:8000/api/v1/llm/query -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"unit":"SC-126","question":"Is SC-126 healthy?","persona":"plant_manager"}'
```

The `worker` service auto-loads the six machines from `Datasets/` on first start
and keeps the analysis current on an interval.

---

## Repository layout

```
senseminds/
├── domain/            immutable domain models, enums, value objects
├── catalog/           asset/sensor/threshold reference data
├── ingestion/         TimeSeriesSource + CSV/DB adapters, ReadingSink, validation
├── engines/           7 deterministic analytics engines
├── findings/          immutable Finding contract + assembler
├── knowledge_graph/   graph model, repository, idempotent projector
├── rules/             rule definitions + forward-chaining evaluator
├── pattern_learning/  unsupervised novelty / regime discovery (Phase B)
├── forecasting/       pluggable, backtested short-horizon forecasting (Phase B)
├── llm/               grounded communication layer (ADR-018): retrieval, prompt,
│                      citation validator, stub + Groq adapters
├── repositories/      aggregate-root repository ports + models
├── application/       analysis pipeline + AnalysisUseCase (atomic orchestration)
├── infrastructure/    DB engine, migrations, Postgres repositories, graph store,
│                      artifact store, logging
├── api/               FastAPI app, routers, JWT auth, request logging
└── workers/           continuous analysis worker
frontend/              React + Vite + Tailwind dashboard (validated light palette)
deployment/            Dockerfile, docker-compose.yml, .env.example
docs/architecture/     ADR-001 … ADR-019
tests/                 226 tests (unit + parity + integration)
```

---

## Next steps (roadmap)

**MVP-completing (near term)**
- **Wire Pattern Learning + Forecasting into the live `AnalysisUseCase`** so
  novelty/regime/forecast findings persist alongside the deterministic ones.
- **Pin dependencies** (lockfile) — the Docker image currently installs unpinned
  newer numpy/scipy/pandas; pin them so deterministic outputs never drift.
- **API hardening** — pagination, rate limiting, refresh tokens / OIDC.

**Production hardening (recommended)**
- OpenTelemetry tracing + per-engine metrics; alerting.
- Artifact/KG retention policies; backup & restore (DR).
- Streaming ingestion adapter (OPC-UA / MQTT / historian) behind the existing
  `TimeSeriesSource` / `ReadingSink` seam.

**Future**
- **Phase C — supervised learning** (failure prediction / RUL) once labeled
  maintenance events accumulate. Human feedback on learned findings is already
  the label-bootstrap store.

---

## Principles (kept throughout)

- **Deterministic facts vs. learned hypotheses** are separated at every layer.
- **Everything is explainable, reproducible, and traceable** to its evidence.
- **The LLM never computes or invents** — grounded, cited, register-aware, and
  free to say "insufficient evidence."
- **Nothing frozen is changed** without a genuine defect.

_Architecture and rationale: see [`docs/architecture/`](docs/architecture/)._
