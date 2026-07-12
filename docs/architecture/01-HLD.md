# SenseMinds 360 — High-Level Design

## 1. What already exists (and must be reused, not rebuilt)

Phases 1–2 already produced deterministic engines as scripts under
`Datasets/scripts/` (`step1`…`step12`, `common.py`) plus their computed
artifacts under `Datasets/reports/` and `Datasets/reports/data/`. These are
not throwaway prototypes — they are the **first working implementation of the
platform's analytics core**. The platform is therefore a *refactor-and-extend*
of proven logic into typed, tested packages, **not a greenfield build**.

Mapping of existing work to platform layers:

| Existing (script) | Becomes platform component |
|---|---|
| `extract_pdfs.py` | Ingestion / Data Acquisition |
| `step1_inspection`, `step5_data_quality` | Data Engineering + Data Quality |
| `step2_sensor_mapping` | Sensor Mapping (feeds Knowledge Graph) |
| `step3_threshold_mapping`, `step10_threshold_validation` | Threshold Engine |
| `step4_engineering_stats` | Statistics Engine |
| `step6_operating_states` | Operating State Engine |
| `step8_operating_envelope` | Operating Envelope Engine |
| `step9_runtime_behavior` | Runtime Analytics |
| `step11_sensor_reliability` | Sensor Reliability Engine |
| `step7_sensor_relationships`, `step12_engineering_insights` | Engineering Intelligence (feeds KG + Rule Engine) |

The markdown reports are **presentation artifacts**, not the knowledge source.
The *inter-layer knowledge* is the structured output (the `data/*.csv`
artifacts and, going forward, typed Pydantic result objects). ADR-004.

## 2. The corrected architecture — a DAG, not a chain

The brief mandated a strict 16-step linear flow. That is rejected (ADR-003).
The true dependency graph:

```text
                        ┌─────────────────────┐
   Industrial Assets ──▶│  Ingestion (PDF/CSV/ │
   (PDF log sheets,     │  future: OPC-UA,     │
    future live feeds)  │  MQTT, historian)    │
                        └─────────┬───────────┘
                                  ▼
                        ┌─────────────────────┐
                        │ Data Engineering +  │  ← Data Quality is a
                        │ Validation + Quality│    cross-cutting gate,
                        └─────────┬───────────┘    not a downstream step
                                  ▼
              ┌──────────────── Validated Time-Series ────────────────┐
              ▼                   ▼                    ▼               ▼
     ┌──────────────┐   ┌──────────────┐    ┌──────────────┐  ┌──────────────┐
     │  Statistics  │   │  Threshold   │    │  Operating   │  │   Sensor     │
     │   Engine     │   │   Engine     │    │State Engine  │  │ Reliability  │
     └──────┬───────┘   └──────┬───────┘    └──────┬───────┘  └──────┬───────┘
            │                  │          ┌────────┴────────┐        │
            │                  │          ▼                 ▼        │
            │                  │  ┌──────────────┐  ┌──────────────┐ │
            │                  │  │  Operating   │  │   Runtime    │ │
            │                  │  │  Envelope    │  │  Analytics   │ │
            │                  │  └──────┬───────┘  └──────┬───────┘ │
            └──────────┬───────┴─────────┴─────────────────┴─────────┘
                       ▼
             ┌────────────────────┐        Everything above is DETERMINISTIC.
             │  Knowledge Graph   │◀─── Sensor mapping + equipment taxonomy
             │ (equipment↔sensor↔ │     seed the graph; engine outputs attach
             │ state↔failure-mode)│     as evidence nodes/edges.
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │   Rule Engine      │  Deterministic, explainable, evidence-linked.
             │ (evidence → likely │  Delivers ~80% of diagnostic value with
             │  condition)        │  100% traceability. Built BEFORE any ML.
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │  Health Scoring    │  Deterministic hierarchical aggregation:
             │ sensor→subsystem→  │  sensor→subsystem→equipment→plant.
             │ equipment→plant    │  Driven by rules + reliability + envelope.
             └─────────┬──────────┘
                       ▼
        ┌──────────────┼───────────────────────────┐
        ▼              ▼                           ▼
┌────────────────┐ ┌────────────────┐   ┌────────────────────────┐
│ Phase B —      │ │ Phase C —      │   │  LLM Reasoning Node     │
│ Pattern Learn  │ │ Supervised ML  │   │ (LangGraph). Narrates & │
│ (unsupervised, │ │ (needs labels; │──▶│ explains over STRUCTURED│
│  label-free):  │ │  DEFERRED till │   │ evidence. Never computes│
│ clustering,    │ │  labels exist) │   │ numbers or invents      │
│ embeddings,    │ │ failure/RUL    │   │ thresholds. Cites       │
│ forecasting,   │ └───────┬────────┘   │ artifact IDs. ADR-009.  │
│ novelty (advis)│         │            └───────────┬─────────────┘
└───────┬────────┘         │                        │
        │  novelty triage by engineer = a LABEL ─────┼──▶ (feeds Phase C)
        └──────────────────┴────────────────────────▶│
                                        ▼             │  Phase B/C outputs are
                            ┌────────────────────────┐│  extra evidence inputs to
                            │  API (FastAPI) +        ││  the LLM, not gates on it.
                            │  Dashboard              ││  ADR-007.
                            └────────────────────────┘┘
```

ML is a three-phase model (ADR-007): **A** deterministic (everything above the
fan-out, building now), **B** unsupervised pattern learning + forecasting
(label-free; enriches A, never replaces it; novelty is advisory "unlike
history", not "fault"), **C** supervised prediction (built only once labels
exist). Phase B is designed to harvest Phase C's labels via engineer triage.

Key correctness points this fixes:
- **Health scoring does not depend on ML.** In the mandated chain it sat
  *after* ML; that would make the platform's core health signal unavailable
  until (deferred) models exist. Health is deterministic and available day one.
- **The LLM consumes the KG, Rules, and Health in parallel**, not "after ML in
  a line." ML output, *when it exists*, is one more evidence input to the LLM,
  not its upstream gate.
- **Data Quality is a cross-cutting gate**, not a station on a conveyor. It can
  veto/annotate any record before any engine consumes it.

## 3. Layered boundaries (Clean Architecture / DDD applied honestly)

```
domain/          Pure engineering concepts + invariants. No I/O, no pandas.
                 Entities: Asset, Subsystem, Sensor, Reading, OperatingState,
                 Threshold, Envelope, FailureMode, Rule, Finding, HealthScore.
                 Value objects: EngineeringUnit, Severity, Confidence, Evidence.

application/     Use-cases orchestrating domain + engines. One use-case per
                 platform capability (RunQualityGate, SegmentStates, EvaluateRules,
                 ScoreHealth, DiagnoseAsset, NarrateFindings). No framework code.

engines/         The deterministic analytics (refactored steps 1–12). Each engine
                 is a stateless service with a typed input contract and a typed
                 result object. Pandas/Polars lives HERE and nowhere above it.

infrastructure/  Adapters: ingestion sources, artifact store, KG repository
                 (embedded now / Neo4j later — behind one interface), LLM client,
                 config, logging, metrics, tracing.

interfaces/      FastAPI routes, CLI, dashboard BFF. Thin. Maps DTOs↔use-cases.
```

Dependency rule: `interfaces → application → domain`; `engines`/`infrastructure`
implement interfaces the inner layers declare. Domain depends on nothing.

## 4. Inter-layer data contracts (the real "reuse existing reports")

Every engine emits a **versioned typed result** (Pydantic v2), persisted to an
artifact store with a stable ID and provenance (source unit, code version,
input hash, timestamp). Downstream layers consume **these objects**, never
another engine's internal state. This is what "no module duplicates earlier
computations" actually means in practice. Examples:

- `StatisticsResult { unit, sensor, min, max, p5..p95, iqr, cv, ... , provenance }`
- `OperatingStateResult { unit, machine, cutpoints[], episodes[], state_summary[], provenance }`
- `ThresholdValidation { unit, sensor, band, pct_outside, per_state_breakdown, verdict, provenance }`
- `ReliabilityScore { unit, sensor, missing_pct, flatline, fault_code, noise, score }`
- `Finding { asset, evidence[Evidence], likely_condition, confidence, rule_id, provenance }`

`Evidence` links a Finding back to the exact artifact IDs that justify it —
this is the mechanism that makes "every recommendation references evidence"
true by construction, not by convention.

## 5. Knowledge Graph — schema sketch

Nodes: `Plant, Area, Equipment(Asset), Subsystem, Sensor, OperatingState,
Threshold, FailureMode, MaintenanceAction, EngineeringRule`.
Edges: `HAS_SUBSYSTEM, HAS_SENSOR, MEASURED_BY, EXHIBITS_STATE,
GOVERNED_BY(threshold), INDICATES(sensor→failure_mode), MITIGATED_BY,
DEPENDS_ON, EVIDENCE_FOR`.

The graph is seeded from the **already-built sensor mapping + equipment
taxonomy** (SC-126/114/104 refrigeration compressors; COM/NP utility air +
N₂ plant). Engine outputs attach as time-stamped evidence. The Rule Engine
and LLM reason **over the graph**, which is what makes reasoning explainable
and traceable. Storage decision: embedded first, Neo4j later — ADR-005.

## 6. Anti-hallucination posture (non-negotiable for industrial use)

The LLM never: computes a statistic, invents a threshold, asserts a failure
without a linked `Finding`, or overrides a deterministic rule. It only:
selects, orders, and *explains in natural language* evidence that already
exists as structured objects, and every claim in its output carries a citation
to an artifact/finding ID. If the evidence is absent, the correct output is
"insufficient evidence," never a plausible guess. ADR-009.
