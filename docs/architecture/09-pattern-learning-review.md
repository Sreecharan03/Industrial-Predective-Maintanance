# ADR-016 — Pattern Learning: Architecture Review (Phase B)

Status: **ACCEPTED (2026-07-10)** with four owner refinements — see §15. This is
**Phase B** of ADR-007 (A deterministic — done; B pattern learning, label-free —
this ADR; C supervised — deferred until labels). Builds on ADR-013 (Findings),
ADR-014/015 (Graph, Rules).

## 0. Context and the hard constraint

The dataset still has **no failure labels**. So Phase B is strictly
**unsupervised + forecasting** — pattern *discovery*, never failure
*prediction*. Its purpose is to surface hypotheses an engineer can triage; that
triage is what eventually produces the labels that unlock Phase C (the
label-bootstrap loop, ADR-007).

## 1. The boundary — deterministic reasoning vs learning

| Deterministic layers (Analytics → Findings → Rules) | Pattern Learning |
|---|---|
| Produce **facts** + explainable diagnoses | Produces **hypotheses** |
| Bit-for-bit reproducible | Model-derived, *reproducible* (seeded), not exact |
| `origin = DERIVED / DIAGNOSED` | `origin = LEARNED` only |
| Consumed as authoritative inputs | **Advisory only**, never authoritative |

**The boundary rule:** learning **reads** deterministic outputs (validated data
via an engineered feature pipeline, DERIVED findings, engine results, graph
structure); it **writes only** `LEARNED`-origin hypotheses (LEARNED findings +
`SUGGESTS`/`PRECEDES` edges + `DiscoveredPattern` nodes), each confidence-scored,
model-versioned, and marked `status=hypothesis`. Deterministic findings and
rules **never** treat a LEARNED output as authoritative; a rule may reference it
only as **optional, low-weight corroboration** (ADR-015 §10), never as a required
antecedent. Remove the entire ML layer and **nothing deterministic changes** —
ML is strictly additive.

## 2. What Pattern Learning IS / IS NOT

- **IS:** unsupervised discovery of structure and novelty in *validated,
  engineered* behaviour — multivariate operating regimes, "today is unlike
  history" novelty, and (later) short-horizon forecasts tied to a decision.
- **IS NOT:** failure prediction, RUL, fault classification (all Phase C, need
  labels); a source of facts; a producer of DERIVED/DIAGNOSED findings; an
  autonomous rule author.

## 3. First-release model set (staged, justified)

**Ship in the first release:**
1. **Unsupervised novelty scoring — Isolation Forest.** Over engineered
   per-window multivariate features: "this window is unlike the machine's
   history." Emitted as a `NOVELTY_ELEVATED` LEARNED finding with a score,
   **framed as 'unlike history', never 'fault'**, and ranked *behind* the
   deterministic rules (ADR-007 guardrail). Chosen over autoencoders for the
   first release: cheaper, no training instability, naturally handles the
   modest feature dimensionality, and its per-feature attribution aids
   explanation.
2. **Operating-regime clustering — Gaussian Mixture / HDBSCAN.** Multivariate
   regimes across all sensors — an **enrichment** of the deterministic 1-D
   operating states (ADR-007), not a replacement. Emitted as
   `OPERATING_REGIME_DISCOVERED` LEARNED findings + `DiscoveredPattern` nodes.

**Design now, ship next increment: forecasting.** Short-horizon forecasts of
key sensors (discharge/oil temp, pressure, power) to give **lead time before a
threshold breach**. Staged because it needs regular-cadence resampling + gap
handling infrastructure and is only valuable tied to a decision — not worth
bundling into the first release. Documented so the contract accommodates it.

## 4. Feature contract (engineered, not raw ticks)

Models never consume raw readings directly. A deterministic **FeaturePipeline**
builds per-window feature vectors from **validated** data + engine outputs:
per-window sensor aggregates, operating-state one-hot, **envelope-relative
position** (where a reading sits in its P5–P95 band), and **reliability
weighting** (down-weight untrustworthy sensors). Features carry a
`feature_schema_version`. This is the ADR-007 rule honoured: *features derived
from validated data + engineered representations, never raw sensor ticks*.
**DIAGNOSED/LEARNED findings are never features** (circularity); only DERIVED
findings + engine outputs + engineered signals are.

## 5. Learned outputs as Knowledge-Graph hypotheses (not facts)

LEARNED outputs enter the graph clearly quarantined from facts:
- **Nodes:** `DiscoveredPattern` (a regime/novelty pattern) and `LearnedModel`
  (model_id/version); LEARNED FindingConditions (`origin=learned`,
  `status=hypothesis`).
- **Edges:** `SUGGESTS` (LEARNED finding → hypothesis), `PRECEDES` (learned
  temporal/causal sequence), `DISCOVERED_BY` (pattern → model). **Every** learned
  node/edge carries `confidence`, `support` (data volume), `model_version`, and
  `status=hypothesis`.
- Consumers can **filter by origin/status**, so the LLM and dashboard always
  present *engineering facts* and *learned hypotheses* as visually and
  semantically distinct. **No LEARNED output is ever auto-promoted to a rule or
  fact** — a human curates it into a deterministic rule (ML proposes, humans
  dispose).

## 6. How contamination of deterministic findings is prevented

1. **Separate origin lane.** LEARNED is a distinct `FindingOrigin`; the Findings
   assembler and Rule Engine can only emit DERIVED/DIAGNOSED; the Pattern
   Learning layer can only emit LEARNED. Enforced by which component writes.
2. **No ML feedback loop.** DIAGNOSED/LEARNED findings are excluded from the
   feature set (ADR-013) — learning cannot train on its own or the rules'
   outputs.
3. **Additive-only, advisory.** Rules may use LEARNED signals only as optional
   corroboration with capped weight; a LEARNED novelty can raise attention but
   can never *be* a diagnosis or change a deterministic verdict.
4. **Deterministic independence.** The deterministic pipeline computes
   identically with the ML layer absent; parity tests remain untouched.
5. **Provenance separation.** LEARNED findings carry *model* provenance
   (model_id/version/seed/training-window), distinct from engine provenance, so
   their nature is always legible.

## 7. Reproducibility & model versioning

ML is not bit-deterministic like the engines, but must be **reproducible**:
fixed **seeds**, pinned **model versions**, and a **snapshotted training input
hash**, so `(model_version, seed, feature snapshot) → identical output`. A
**ModelRegistry** stores each model artifact with `model_id, version,
trained_at, training_window, feature_schema_version, hyperparameters, seed`.
Every LEARNED finding references the `model_version` that produced it. Tests
assert **reproducibility** (same seed+data ⇒ same clusters/scores), not Phase-2
parity (no Phase-2 ML exists).

## 8. Interfaces (repository/ports — embedded first, ADR-005 style)

```
FeaturePipeline   build(validated data + engine outputs) -> FeatureFrame   (deterministic)
PatternModel      fit(features) ; score/assign(features) -> LearnedOutput   (interface)
   IsolationForestNovelty, RegimeClusterer  (implementations)
ModelRegistry     save/load versioned model artifacts + metadata
PatternProjector  project LEARNED outputs -> KG hypotheses (idempotent, like the findings projector)
```

## 9. Knowledge-Graph integration

New node types `DiscoveredPattern`, `LearnedModel`; new edges `SUGGESTS`,
`PRECEDES`, `DISCOVERED_BY`. LEARNED findings reuse the existing
FindingCondition projection (with `origin=learned`, `status=hypothesis`
properties) and the same idempotent projector, so the graph stays one coherent
store with facts and hypotheses cleanly separable by property.

## 10. Edge cases

Sparse/short history → model not fit (insufficient support) → no hypotheses
emitted, not an error. Multi-week gaps → windows spanning gaps excluded from
features. Untrustworthy sensors → down-weighted in features; a novelty driven
solely by a drifting sensor is annotated as such. Regime instability → clusters
below a support threshold are dropped. Model drift → new model version; old
LEARNED findings reference the old version and can be superseded. Single-unit vs
cross-plant → models are per-unit first; cross-asset pattern mining is a later
increment.

## 11. Consumers

- **Rule Engine:** may consume LEARNED signals **only** as optional, capped-
  weight corroboration; never as required antecedents (§1, §6).
- **Pattern Learning ↔ future Phase C:** engineer triage of LEARNED novelty
  produces the labels that unlock supervised ML (label-bootstrap loop). Learned
  sequences become `PRECEDES` edges that Phase C may later validate.
- **LLM (future):** presents LEARNED hypotheses **distinctly** from facts, cites
  `model_version` + confidence, and never treats a hypothesis as a diagnosis.

## 12. Explicitly deferred (not in Phase B)

Supervised failure classification, RUL, maintenance-optimization (Phase C, need
labels); autonomous rule creation; the LLM; forecasting *implementation*
(designed here, shipped in Phase-B increment 2).

## 13. Example — SC-126 (honest expectation)

SC-126 is a stable, healthy baseload machine, so Phase B will likely find
**little novelty** (low Isolation-Forest scores) and clustering will
**re-discover the deterministic regimes** (full-load-dominant) — *confirming*,
not contradicting, the deterministic states. That is the correct, honest
outcome: on healthy equipment the learning layer mostly agrees with the facts
and stays quiet. Its value shows on machines/periods that *do* deviate — where a
`NOVELTY_ELEVATED` hypothesis flags "unlike history" for engineer triage, kept
strictly separate from (and subordinate to) the deterministic diagnosis.

## 14. Decision & next step

Adopt: the deterministic/learning boundary (§1); LEARNED-only outputs as graph
hypotheses (§5); contamination prevention via separate lane + no-feedback +
additive-only (§6); reproducibility via seeds + a ModelRegistry (§7); the §8
interfaces; first-release **Isolation Forest novelty + regime clustering**, with
forecasting staged (§3).

**Awaiting approval.** On the go-ahead, the first implementation unit would be
the `FeaturePipeline` + `ModelRegistry` + `PatternModel` interface + the
Isolation-Forest novelty model emitting `LEARNED` findings, with reproducibility
and boundary-isolation tests — then regime clustering, then the KG hypothesis
projection. No supervised ML, no LLM.

## 15. Accepted refinements (owner review, 2026-07-10)

**R1 — Model Health (trust the model, like we trust sensors).** A lightweight
`ModelHealth` accompanies every model run: `coverage` (fraction of windows with
usable features), `feature_completeness`, a `drift_indicator` (recent- vs
early-window feature-distribution shift), and `reproducible` status (seeded).
This is the *Sensor Reliability of models* — a LEARNED finding from a
low-health model is discounted/flagged exactly as a diagnosis from an
untrustworthy sensor is.

**R2 — Human-feedback interface (foundation for Phase C).** Define the contract
for future engineer validation of LEARNED findings — verdicts `CONFIRMED_NOVELTY`
/ `EXPECTED_BEHAVIOUR` / `FALSE_POSITIVE` + note + author + timestamp, keyed by
the finding `identity_key`. **Not consumed in Phase B** (it does not influence any
model or output), but it is the store that becomes Phase C's **labels** (the
label-bootstrap loop). Implemented as a model + repository interface only.

**R3 — Pattern lifecycle (metadata, never a fact).** `DiscoveredPattern` carries
a lifecycle: `EMERGING → STABLE → DECLINING → INACTIVE`, computed from the
pattern's occurrence trend across windows. It is explicitly **metadata on a
hypothesis**, not a deterministic fact, and is stored on the pattern node with
its confidence/support.

**R4 — Explainable learning (why, not just a score).** Every LEARNED finding
exposes its **principal contributing features** (the sensors/engineered features
that drove the novelty, with their deviation) alongside the novelty score — via
its `evidence`. The Dashboard and LLM must be able to say *"unusual because
discharge-temp and oil-temp are jointly far above their historical band,"* not
merely *"anomaly score 0.87."*
