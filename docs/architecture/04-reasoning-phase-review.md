# ADR-011 — Deterministic-Core Review & Reasoning-Phase Sequencing

Status: **Proposed** (2026-07-10). Supersedes the original roadmap ordering for
Milestones 3–4 (see 03-build-roadmap.md). No code until accepted.

## Context

The deterministic analytics core is built and parity-locked: Statistics,
Operating State, Operating Envelope, Threshold, Operational Timeline (97 tests
green). Before implementing the reasoning phase (Health, Rules, Knowledge
Graph) this ADR reviews whether the core is actually complete, audits the
engine dependency graph, and designs the next phase from first principles
rather than assuming the original roadmap is optimal.

---

## 1. Is the deterministic layer complete? — **No. One capability is missing.**

**Finding 1.1 — Sensor Reliability engine is missing.** Phase-2 had a Sensor
Reliability analysis (step11: missing-rate, flatline/frozen-value, fault-code,
noise → a per-sensor reliability score + ranking). It is **not** among the five
built engines, yet Health scoring depends on it (a health score must discount
sensors that are untrustworthy). The deterministic core is therefore ~90%
complete; Reliability is the gap.

- It is cheap: a thin engine consuming the existing `QualityResult` (which
  already computes missing/flatline/fault-code) + `StatisticsResult`, plus a
  noise metric it computes itself (owned nowhere else). It is parity-testable
  against `sensor_reliability_ranking.csv`.

**Finding 1.2 — the catalog does not define subsystems.** `build_asset`
populates sensors but leaves `subsystems=()`. Health is hierarchical
(sensor → subsystem → equipment → plant); the subsystem→sensor grouping is
catalog data and must be populated before Health can roll up. (This is catalog
data, **not** a Knowledge-Graph responsibility — see §3.)

---

## 2. Dependency-graph audit — verified findings

Actual engine graph (confirmed from code):

```
series ─▶ Statistics ─▶ Envelope ─▶ Threshold ─┐
series ─▶ Operating State ─────────────────────┼─▶ Operational Timeline
                                    (Threshold ─┘ optional, for context)
```

**Finding 2.1 (defect) — Threshold consumes `OperatingEnvelopeResult` but does
not use it.** Verified: the only reference to `envelope` in the Threshold
engine is the unit-equality check; the interpretation uses `pct_outside` alone.
The engine advertises a dependency it does not exercise — a misleading contract
and needless coupling. **Fix:** either (a) *use* it — enrich the interpretation
with the envelope's P5–P95 window ("threshold sits above the observed operating
window") which is high-value for Health/LLM, or (b) drop the parameter and take
`series` + catalog only. **Recommendation: (a) use it** — the envelope-vs-
threshold comparison is exactly the engineering judgment downstream consumers
need, so the dependency becomes real and justified.

**Finding 2.2 (inconsistency) — immutability is not uniform.** Envelope,
Threshold, Timeline results are frozen; Statistics and Operating State results
are not. New reasoning results will be frozen. **Fix:** make the `EngineResult`
base `frozen=True` so every result is immutable by default; remove the
per-model override. (Touches two "stable" modules, but parity tests guard the
change — this is a genuine consistency defect.)

**Finding 2.3 (duplication) — provenance construction and the `_Frozen` base
are copy-pasted.** `Provenance(...)` is hand-built in all 5 engines; `_Frozen`
is redefined in 3 model modules. With 4 more engines coming (Reliability,
Health, KG, Rules) this becomes 9×. **Fix:** extract a minimal `BaseEngine`
(name/version + `make_provenance`) and a single shared frozen base now — the
pattern is proven across 5 engines (this is the "extract when proven" trigger I
set in ADR-002/point-2, now reached).

**Finding 2.4 (gap) — no orchestration layer.** Engines are wired by hand in
every test and dry-run. Health and Rules each fan in from 4–5 upstream results;
ad-hoc positional wiring will not scale. **Fix:** introduce an application-layer
**pipeline** that runs the DAG once and produces a typed **`AnalysisContext`**
(a bundle of all engine results for a unit). Health/Rules/KG then consume one
container instead of 5 positional arguments — cleaner contracts, one place to
evolve the DAG.

**Finding 2.5 (deferred, not a defect) — no per-timestamp threshold timeline.**
The Timeline engine carries threshold *context* but cannot emit "entered
warning region" *events* because that needs a per-timestamp threshold state the
Threshold engine (rightly) does not expose. If the Rule Engine needs "time in
warning region", extend the **Threshold** engine to emit a threshold timeline —
never let another engine evaluate thresholds (ownership rule holds).

---

## 3. Next-phase design (first principles) & responsibilities

- **Sensor Reliability** — per-sensor trustworthiness. Deterministic. Depends
  on Quality + Statistics. Pure prerequisite for Health.
- **Health Scoring** — deterministic hierarchical aggregation (sensor →
  subsystem → equipment → plant). Inputs: Reliability (trust), Threshold
  (breach severity), Envelope (excursion), Timeline (utilization/idle context),
  catalog subsystems. **Does not need Rules or the KG** — it is a bottom-up
  rollup. Highest immediate, tangible value (a health number for the
  dashboard). Available day one.
- **Knowledge Graph** — the *semantic substrate*: equipment ↔ subsystem ↔
  sensor ↔ threshold ↔ failure-mode ↔ maintenance-action, with engine results,
  health scores, and (later) findings attached as time-stamped **evidence**.
  It is an integration/indexing layer, most valuable once there are rich
  outputs to hold and right before something needs to *reason over* it.
- **Rule Engine** — diagnosis. Consumes the most inputs (engine results +
  health + KG relationships) and produces `Finding`s (evidence + confidence).
  Most complex; benefits from both KG (sensor↔failure-mode structure) and
  Health (as a signal). Belongs last.

### Ordering decision (diverges from the original roadmap)

**Recommended sequence:**
**Reliability → Health → Knowledge Graph → Rule Engine**
(preceded by the §2 remediations).

The original roadmap put the Knowledge Graph *before* Health and Rules. This
ADR moves **Health ahead of the KG**. Justification:

1. **Responsibilities / data flow:** Health depends only on deterministic
   engine outputs + catalog subsystems — none of which is the KG. The catalog
   already supplies the hierarchy Health needs. Building the KG first would be
   laying a foundation with nothing yet to hold.
2. **Explainability / value:** Health is the platform's first end-to-end
   *verdict* ("equipment health = 82%, driven by …"). Shipping it early gives a
   tangible, defensible output and reuses the proven "consume-contracts" pattern
   once more before the harder components.
3. **KG earns its place right before Rules:** the KG's payoff is as the
   reasoning substrate for the Rule Engine and LLM. Built third — seeded from
   the catalog and populated with real engine results *and* health scores — it
   holds meaningful evidence from day one, and the Rule Engine consumes it
   immediately after.
4. **Maintainability:** Rules last means the most-coupled, most-complex
   component is built when every input contract it needs (including Health and
   the KG) already exists and is stable — no churn from evolving upstreams.

---

## 4. Contracts (consumed / exposed)

| Component | Consumes | Exposes |
|---|---|---|
| **Sensor Reliability** | `QualityResult`, `StatisticsResult`, `IngestedSeries` (noise) | `ReliabilityResult` — per-sensor score + components + rank |
| **Health Scoring** | `ReliabilityResult`, `ThresholdResult`, `OperatingEnvelopeResult`, `OperationalTimelineResult`, catalog subsystems | `HealthResult` — sensor→subsystem→equipment→plant scores, each with contributing factors + `Evidence` |
| **Knowledge Graph** | catalog (seed), all `EngineResult`s, `HealthResult`, later `Finding`s | `KnowledgeGraphRepository` — query API returning nodes/edges + evidence ids (read model for Rules + LLM) |
| **Rule Engine** | engine results (via `AnalysisContext`), `HealthResult`, KG relationships | `Finding`s (existing domain entity) — evidence + confidence + rule id |

All new results keep the established shape: immutable, `artifact_id` +
`Provenance`, evidence separated from domain output — so the KG and future LLM
can cite everything by id.

---

## 5. Architectural risks to address before further implementation

1. **Threshold–envelope dead coupling** (2.1) — fix before building on the
   Threshold contract, so consumers don't inherit a misleading dependency.
2. **Immutability inconsistency** (2.2) — freeze the `EngineResult` base now,
   before more results are added on the old pattern.
3. **Provenance / frozen-base duplication** (2.3) — extract `BaseEngine` +
   shared frozen base before adding 4 more engines.
4. **No orchestration / result bundle** (2.4) — introduce the pipeline +
   `AnalysisContext` before Health, which is the first true fan-in consumer.
5. **Catalog subsystems missing** (1.2) — populate before Health's rollup.
6. **KG store choice** — honour ADR-005: embedded graph behind a repository
   interface now; defer Neo4j.
7. **Rule conflict/priority model** — design deterministic conflict resolution
   and confidence up front (ADR-006) so rules don't accumulate ad hoc.

## Decision

Adopt the sequence **[remediate §2.1–2.4 + populate subsystems] → Sensor
Reliability → Health → Knowledge Graph → Rule Engine**. The remediations are
small, parity-guarded, and prevent compounding debt; Reliability closes the
deterministic core; Health delivers early deterministic value; the KG is built
as the reasoning substrate immediately before the Rule Engine consumes it.
