# ADR-013 — Engineering Findings Layer: Architecture Review

Status: **ACCEPTED (2026-07-10)** with three owner refinements — see §10. They
sharpen the immutability boundary (workflow state and prioritization move *out*
of the Finding) without changing the contract of §4. Builds on ADR-012.

## 1. First principles — what this layer is

The Findings layer is a **deterministic interpretation layer**, not an
analytics engine. It is a pure, reproducible function of already-validated
engine results: it **interprets** (produces engineering statements) and never
**recomputes** analytics. Its output — the `Finding` — is the single language
consumed by the Knowledge Graph, Rule Engine, Pattern Learning, LLM, Dashboard,
and external APIs.

```
Engine results (measurements)  ──▶  Findings layer  ──▶  Findings (claims)
  Statistics/State/Envelope/           (deterministic        the canonical
  Threshold/Timeline/Reliability/       interpretation)      language above
  Health  (in the artifact store)                            this line
```

## 2. What a Finding IS and IS NOT

**A Finding IS** a validated, human-meaningful engineering *claim* about the
equipment, carrying severity, confidence, and evidence:
- "Operating threshold inconsistent with the historical operating envelope."
- "Sensor reliability degraded (drift)."
- "Equipment operating continuously at full load."
- "Equipment health reduced."

**A Finding IS NOT** a measurement or configuration: raw pressure value,
percentile, histogram, threshold config, statistics table, time-series. Those
are **evidence** a Finding *references* — they live in engine results in the
artifact store, not in the Finding.

The distinction is claim vs. measurement. If it was computed, it's evidence. If
it interprets what the computation *means*, it's a Finding.

## 3. Taxonomy — three orthogonal axes (improves the flat list)

The suggested list (Operational / Reliability / Health / Threshold / Runtime /
Equipment / Subsystem / Plant) mixes two different questions — *what the finding
is about* and *what level it applies to*. A "Health Finding" can be at
subsystem **or** equipment scope, so a flat list forces false choices. The
review therefore splits the taxonomy into **three orthogonal axes** plus an
enumerable type:

- **Category** (what it is about): `THRESHOLD`, `RELIABILITY`, `HEALTH`,
  `RUNTIME`, `ENVELOPE`, `DATA_QUALITY`, `DIAGNOSTIC` (rule-derived),
  `ANOMALY` (pattern-learning, future).
- **Scope** (what level): `SENSOR`, `SUBSYSTEM`, `EQUIPMENT`, `PLANT`.
- **Origin** (who produced it, and thus how much to trust the mechanism):
  `DERIVED` (deterministic from one engine verdict), `DIAGNOSED` (Rule Engine,
  multi-signal), `LEARNED` (Pattern Learning, future).
- **`finding_type`** — the specific machine-readable kind within a category,
  e.g. `THRESHOLD_MISSPECIFIED`, `THRESHOLD_BREACH_CRITICAL`,
  `RELIABILITY_DRIFT`, `RELIABILITY_FLATLINE`, `HEALTH_DEGRADED`,
  `RUNTIME_CONTINUOUS_FULL_LOAD`, `RUNTIME_EXTENDED_IDLE`,
  `ENVELOPE_MULTIMODAL`. This enum is the stable key everything switches on.

Why: category × scope × origin classify every finding without collision;
`finding_type` is the extensible vocabulary. New capabilities add types/origins
without reshaping the taxonomy.

## 4. The Finding contract (immutable)

Answers what / where / why / severity / confidence / evidence / source / when /
provenance:

| Field | Purpose |
|---|---|
| `finding_type` (enum) | **What** — machine-readable kind |
| `category`, `scope`, `origin` (enums) | classification axes (§3) |
| `summary` | **What**, human-readable one line |
| `detail` | **Why**, the engineering rationale |
| `target_key` | **Where** — the scoped entity (sensor/subsystem/…) |
| `equipment_key`, `subsystem_key` | graph-linking parents (nullable by scope) |
| `severity` (Severity) | ok / info / warning / critical |
| `confidence` (Confidence) | value + rationale (from reliability/derivation) |
| `evidence` (tuple[Evidence], ≥1) | **Why**, deterministic backing (artifact ids + observed values) |
| `source_engine` | **Source** — producing engine or rule id |
| `observed_window` (start,end) | **When** — the history window it pertains to |
| `provenance` | engine, version, input_hash, produced_at (**timestamp**) |
| `identity_key` | deterministic hash(type, scope, target, window) — stable across runs |
| `supersedes` (finding_id \| None) | explicit lifecycle link |

**Determinism is the linchpin.** `identity_key = hash(asset_key, finding_type,
scope, target_key)` is stable across runs and **globally unique** — asset is
included so the same condition on same-named targets of different equipment
(e.g. `oil_pressure` on COM-102 vs COM-110) never collides (implementation
refinement, owner-requested). The observed window is **excluded** from identity
(it grows across runs; including it would break supersession). `finding_id =
hash(identity_key + input_hash)`. Same inputs ⇒ same ids ⇒ idempotent,
dedupable, supersession-friendly.

**Contract revision needed:** the existing domain `Finding` was shaped for the
Rule Engine (required `rule_id`). It must generalise: make rule linkage
optional, add `finding_type`/`category`/`scope`/`origin`/`target_key`/
`observed_window`/`identity_key`. This is the one breaking change this review
mandates — and it is why we are doing the review *before* anything depends on it.

## 5. Evidence

Every Finding references ≥1 `Evidence` (artifact_id + description +
`observed_value`). The **observed_value is inlined**, so the claim is
self-contained and the LLM can explain it *without recomputing analytics and
even if the source artifact is later purged*; the `artifact_id` is for
drill-down to full detail. A Finding with zero evidence is invalid (enforced by
the contract, as today).

## 6. Interactions

```
                    Catalog (structure seed)
                         │
 Engine results ─▶ Findings layer ─▶ Findings ─┬─▶ Knowledge Graph (nodes+edges)
 (artifact store)   (DERIVED)          ▲        ├─▶ Rule Engine ──(DIAGNOSED)──┐
                                       │        ├─▶ Pattern Learning (features) │
                                       └────────┴─▶ LLM (grounded narration)   │
                                        Rule/Learned findings re-enter ◀────────┘
```

- **Knowledge Graph** stores **Findings (nodes), structural taxonomy (from
  catalog), and relationships** (`AFFECTS_SUBSYSTEM/EQUIPMENT`, `EVIDENCE_FOR`,
  `INDICATES(failure_mode)`, `SUPERSEDES`). It does **not** store raw engine
  results — those stay in the artifact store, referenced by evidence id. Rule
  "conclusions" enter the graph as Findings of origin `DIAGNOSED`.
- **Rule Engine**: rules **consume** Findings (+ engine results) and **produce**
  Findings (`DIAGNOSED`). A "conclusion" *is* a Finding — no parallel type.
  Rules never mutate/enrich existing Findings (immutability); they emit **new**
  Findings that reference consumed Findings as evidence (auditable derivation
  chain). Chosen over "rules enrich findings" because enrichment-by-mutation
  breaks immutability and reproducibility.
- **Health**: Health results are a primary *input* to `DERIVED` findings
  (`HEALTH_DEGRADED` at subsystem/equipment scope); Health is not a Findings
  consumer.
- **Pattern Learning**: **`DERIVED` findings become ML features** (typed,
  engine-agnostic, stable — exactly the ADR-007 "features from validated
  outputs, not raw sensor data" rule). **`DIAGNOSED` and `LEARNED` findings do
  NOT feed back as features** (circularity/leakage); they are outputs/labels.
  This asymmetry is a hard rule.
- **LLM**: narrates over Findings only — uniform, cited, confidence-scored —
  never over raw results (ADR-009 anti-hallucination). It reads a Finding and,
  if asked for detail, fetches referenced artifacts; it never recomputes.
- **Dashboard**: operators see **Findings**, ranked by severity × confidence,
  with drill-down to evidence — not percentile tables. Raw outputs are detail
  behind the finding, not the primary view.

## 7. Lifecycle

```
 produce (deterministic)                       new run, same identity_key,
        │                                        newer input_hash
        ▼                                              │
   [ CURRENT ] ───────────────── SUPERSEDES edge ──────┘
        │                                              ▼
        │  window advances / no longer re-derived   [ SUPERSEDED ]
        ▼
   [ STALE ]   (no current finding re-derives this identity_key)
```

Findings are immutable snapshots. **Current / superseded / stale is relational,
not a mutable field**: for a given `identity_key`, the finding with the newest
`input_hash` is current; older ones are superseded (edge in the KG); an
identity_key no longer produced by the latest run is stale. The store/KG
computes this from ids — no field is ever edited.

## 8. Edge cases — deterministic handling

| Case | Handling |
|---|---|
| Duplicate | same identity_key + input_hash ⇒ same finding_id ⇒ idempotent, stored once |
| Conflicting | DERIVED findings can't self-conflict (deterministic from one engine); conflicts only among DIAGNOSED ⇒ Rule Engine priority/confidence resolution (ADR-006); both retained, higher confidence wins downstream |
| Stale | no current finding re-derives the identity_key (see lifecycle) |
| Superseded | newer identity_key match ⇒ SUPERSEDES edge; old marked not-current |
| Low-confidence | retained + flagged; consumers filter by a confidence floor (dashboard/LLM/ML each choose) |
| Multiple per event | allowed; findings share target + observed_window; grouped, not merged |
| Evidence unavailable | inlined `observed_value` keeps the claim valid; drill-down degrades gracefully |
| Missing provenance | invalid ⇒ rejected at construction (provenance required) |
| Version mismatch | `finding_type` is an open enum + `schema_version`; unknown type ⇒ consumer ignores gracefully, never crashes |

## 9. Decision

Adopt: a deterministic Findings **interpretation layer**; the immutable
`Finding` contract of §4 (three-axis taxonomy + `finding_type`); deterministic
`identity_key`/`finding_id`; evidence with inlined observed values; the KG
stores Findings + structure + relationships (not raw results); rules
consume-and-produce Findings (conclusions are Findings); DERIVED findings feed
ML, DIAGNOSED/LEARNED do not; the dashboard and LLM consume Findings only.

Next implementation unit (**awaiting approval**): the `Finding` contract +
a deterministic **Findings assembler** producing `DERIVED` findings from the
Threshold, Health, and Reliability results — then the Knowledge Graph.

## 10. Accepted refinements (owner review, 2026-07-10)

The Finding stays a pure **immutable observation**. Two concerns that *look*
like they belong on it are deliberately kept **outside** it:

1. **Lifecycle unchanged.** `current / superseded / stale` remains relational,
   computed from `identity_key` + `input_hash` (§7). No field is ever mutated.

2. **Operational workflow state lives outside the Finding.** Operator actions —
   `open → acknowledged → resolved` — are a *separate mutable* `FindingWorkflow`
   record, managed by a workflow service (application layer, with the API/
   dashboard), **not** a field on the immutable Finding. Crucially it is keyed
   by **`identity_key`, not `finding_id`**, so an acknowledgement/resolution
   **persists across re-derivation**: when the same condition is re-observed
   next run (new `finding_id`, same `identity_key`), the operator's state
   carries over. Deterministic re-open rule: a `resolved` condition re-opens if
   a newer finding for that `identity_key` returns at *higher* severity. This
   cleanly separates "what the system observed" (immutable) from "what
   operators did about it" (mutable).

3. **Prioritization is downstream policy, not a Finding field.** The Finding
   carries only the raw signals **`severity` + `confidence`**. The alerting/
   dashboard layer computes priority = f(severity, confidence, **asset
   criticality**) — asset criticality being deployment-specific config that must
   not contaminate the deterministic, reproducible Finding. Priority can change
   with policy without ever touching a Finding.

Net effect — a clean three-way separation:
- **Finding** = immutable observation (what + evidence + severity + confidence).
- **FindingWorkflow** = mutable operator state (open/ack/resolved), keyed by identity.
- **Prioritization** = downstream policy (severity × confidence × criticality).
```
