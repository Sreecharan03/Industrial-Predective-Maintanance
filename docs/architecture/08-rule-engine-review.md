# ADR-015 — Rule Engine: Architecture Review (M5)

Status: **ACCEPTED (2026-07-10)** with three owner refinements — see §15. Builds
on ADR-006 (supersedes its sketch), ADR-013 (Findings), ADR-014 (Knowledge
Graph, incl. §10 fault-mechanism/failure-mode extension).

## 1. Primary responsibility

The Rule Engine is a **deterministic reasoning layer**, not an analytics
engine. It computes no statistics, no health, and creates **no DERIVED
findings**. It **reads** the Knowledge Graph (FindingConditions + structure +
history), correlates multi-signal patterns, and **produces**:

- `DIAGNOSED` Findings (a diagnosis *is* a Finding, `origin=DIAGNOSED` — reusing
  the ADR-013 contract; there is no separate "Conclusion" type),
- `INDICATES` edges (finding → fault mechanism / failure mode),
- failure hypotheses and recommended `MaintenanceAction`s.

It writes back through the **same idempotent projector** as the Findings layer,
so diagnoses become FindingCondition nodes exactly like derived findings — one
uniform currency, one lifecycle.

## 2. First principles — what is / isn't a Rule

- **A Rule** is a deterministic implication over *findings and conditions*:
  `antecedent (a pattern of finding-conditions + structural/reliability context)
  → consequent (a diagnostic finding / failure hypothesis / action)`.
  *Example:* "high discharge temp **+** high condenser entering temp **+**
  rising discharge pressure **+** sustained full-load runtime → condenser
  fouling suspected."
- **Not a Rule:** `pressure > 235` (Threshold Engine); a percentile (Statistics);
  any **single-signal** interpretation (that is a `DERIVED` finding, Findings
  layer).

**The boundary:** single-signal interpretation = a DERIVED finding; **multi-
signal correlation into a higher-order engineering conclusion = a rule.** Rules
encode *failure-signature knowledge*, never data thresholds.

## 3. Rule taxonomy (two orthogonal axes — improves the flat list)

The suggested list mixes *what a rule does* with *where it applies*. Split:

- **RuleKind (function):** `DIAGNOSTIC` (infer a fault mechanism), `CORRELATION`
  (link co-occurring conditions), `CONFIRMATION` (corroborate a hypothesis with
  more evidence), `SUPPRESSION` (down-rank/annotate a finding given context, e.g.
  a known-benign threshold mis-spec), `ESCALATION` (raise severity when
  conditions compound), `SAFETY` (protective, highest-priority inference),
  `MAINTENANCE` (recommend an action), `RECOVERY` (detect return-to-normal).
- **RuleScope (applicability):** `PLANT_WIDE`, `EQUIPMENT_CLASS` (all
  refrigeration screw compressors), `ASSET_SPECIFIC` (SC-126 only).

Why: `RuleKind × RuleScope` classifies every rule without collision;
"asset-specific / plant-wide" are *scope*, not kind (same fix as the Findings
taxonomy). Diagnostic rules emit new `category=DIAGNOSTIC` finding types
(`CONDENSER_FOULING_SUSPECTED`, `OIL_SYSTEM_DEGRADATION`, …), extending the
`FindingType` enum.

## 4. Rule contract (immutable definition — no execution state)

```
RuleDefinition (frozen):
  rule_id, version                 # versioned; new version supersedes
  kind (RuleKind), scope (RuleScope)
  applies_to                       # equipment class / asset key(s) / plant
  description, engineering_assumptions[]
  priority (int)                   # safety/criticality ordering
  produced_severity (Severity)
  required_findings[]              # finding_type patterns that MUST be present
  optional_findings[]              # corroborating -> raise confidence
  excluded_findings[]              # must be ABSENT (negative conditions)
  preconditions[]                  # structural/reliability predicates
  produces: FindingSpec            # DIAGNOSED finding template (type, mechanism)
  indicates: fault_mechanism_key?  # -> INDICATES edge
  recommended_actions[]            # MaintenanceAction keys
  confidence_model                 # deterministic formula (below)
  enabled (bool)                   # config, not runtime state
  provenance                       # author, version, source knowledge
```

No `fired`, `last_run`, or any execution state — those are computed per run and
never stored on the definition.

**Confidence model (deterministic):**
`confidence = rule_prior × strength(required) × corroboration(optional) ×
reliability_factor`, where `strength` = aggregate confidence of the matched
required findings, `corroboration` ≥ 1 grows with optional matches, and
`reliability_factor ≤ 1` **discounts the diagnosis by the trust of the sensors
involved** (see §9). Same inputs → same confidence.

## 5. Execution model

- **Forward-chaining to a fixpoint** for batch inference (observed conditions →
  fire all satisfied rules → new findings → repeat until no new `identity_key`
  appears). **Backward-chaining supported for explanation/query** (LLM/dashboard
  ask "why not condenser fouling?" → evaluate that rule's antecedents and report
  what was missing). Hybrid, but the core is forward + deterministic.
- **Deterministic:** yes. Rules are evaluated in a total order (`priority desc,
  rule_id asc`); the fixpoint result is independent of order because rules are
  **monotonic** (they only *add* findings, never retract).
- **Multiple rules fire per pass**; **rules can trigger rules** (a DIAGNOSED
  finding can satisfy another rule's antecedent — that is the reasoning chain).
- **Cycle prevention (three guards):** (1) the **rule dependency graph**
  (which finding_types each rule consumes/produces) is checked **acyclic at
  load time**; (2) findings are **idempotent by identity_key**, so re-deriving
  an existing condition adds no new fact → the monotonic fixpoint terminates;
  (3) a hard max-iteration bound as a safety net. Monotonicity + idempotent
  identity guarantees termination.
- **Suppression never deletes.** A suppression rule emits a `SUPPRESSES`
  relationship / annotation that consumers respect; the original finding stays
  immutable and auditable. This keeps the whole engine monotonic.

## 6. Conflict resolution (deterministic)

1. Conflicting diagnoses are **both retained** (immutable, auditable) — nothing
   is deleted.
2. A **total ranking** for presentation/action:
   `(priority desc, confidence desc, severity desc, rule_id asc)` — fully
   reproducible.
3. **Priority outranks confidence** (a `SAFETY` rule beats a confident minor
   `DIAGNOSTIC`); within equal priority, confidence decides. Rationale: safety
   must never be outvoted by a confident-but-minor diagnosis.
4. Competing **maintenance actions** dedup by action key; genuinely conflicting
   actions are presented ranked; `ESCALATION`/`CONFIRMATION` rules may combine
   or promote.
5. Contradictory diagnoses may be reconciled by a curated `SUPPRESSION`/
   `CONFIRMATION` rule that explicitly down-ranks one given the other, with
   stated reasoning.

## 7. Knowledge-Graph interaction

- **Rules READ:** FindingCondition nodes (active + historical, incl.
  `occurrences`/recurrence), structural edges (sensor↔subsystem↔equipment),
  reliability conditions, threshold definitions.
- **Rules WRITE only:** `DIAGNOSED` FindingConditions (via the idempotent
  projector), `INDICATES` edges (→ FaultMechanism/FailureMode), `RECOMMENDS`
  edges (→ MaintenanceAction), and `TRIGGERED_BY` edges (diagnosis → the derived
  findings that triggered it — the reasoning chain).
- **Rules NEVER** modify DERIVED findings, analytics results, or structural
  nodes. Read-mostly; append-only writes; deterministic-analytics immutability
  preserved.

## 8. Explainability (self-contained on the finding)

Every `DIAGNOSED` finding carries, so the **LLM never reconstructs** it:
- **Which findings triggered it** — `Evidence` entries + `TRIGGERED_BY` edges to
  the exact DERIVED finding ids/identity_keys.
- **Why it fired** — `rule_id` + version + the satisfied antecedent.
- **Which evidence supports it** — transitively, the triggers' evidence
  artifacts.
- **Engineering assumptions** — copied from the rule definition.
- **Confidence reasoning** — the confidence-model computation as rationale
  (including the reliability discount).
- **Why competing rules did NOT fire** — provided on demand via **backward-
  chaining** (evaluate the near-miss rule, report the missing/excluded
  antecedents). Kept out of the immutable graph as a queryable explanation, so
  the graph stays lean while "why not" is always answerable.

## 9. Edge cases (deterministic handling)

| Case | Handling |
|---|---|
| Missing findings | antecedent unsatisfied → rule does not fire (no error) |
| Conflicting findings | §6 ranking; both retained |
| Missing evidence | inlined `observed_value` keeps triggers usable; diagnosis still valid |
| **Sensor unreliability** | **first-class:** `reliability_factor` discounts confidence when a triggering sensor has `RELIABILITY_DRIFT`/`SENSOR_UNTRUSTWORTHY`; a rule may `exclude` on untrustworthy inputs. Diagnoses inherit the trust of their sensors. |
| Multiple simultaneous failures | multiple DIAGNOSED findings, all retained, ranked |
| Contradictory diagnoses | curated suppression/confirmation; §6 |
| Circular rules | acyclic dependency check at load + monotonic fixpoint + max-iter bound |
| Disabled rules | `enabled=false` → skipped deterministically |
| Versioned rules | `rule_id`+version; newer supersedes; finding records the version that fired |
| Plant/asset overrides | **most-specific scope wins** (ASSET_SPECIFIC > EQUIPMENT_CLASS > PLANT_WIDE), deterministic |
| Unknown equipment | no scope match → no diagnoses (not an error) |
| Partial datasets | rules fire only on present findings; absent inputs → no fire |

## 10. Future ML (Pattern Learning) integration

- **ML creates rules?** **No** — unsafe/unauditable.
- **ML recommends rules?** **Yes** — surfaces frequent finding co-occurrences
  (esp. those preceding labeled failures) as **rule *proposals* for human
  engineering review**. Human curates; ML proposes, humans dispose.
- **ML validates rules?** **Yes** — once failure labels exist, measure how often
  a rule's diagnosis actually preceded failure (rule precision/recall).
- **Rules validate ML?** **Yes** — deterministic rules are **guardrails** on ML
  outputs (flag an ML anomaly that contradicts engineering knowledge).
- **Learned relationships → `PRECEDES` edges?** **Yes** — ML-discovered
  temporal/causal sequences become `PRECEDES` edges (`origin=LEARNED`,
  confidence + provenance), consumable by rules (as *optional* corroboration
  only) and the LLM — but they are **hypotheses, never facts, never auto-
  promoted to rules** without human review.
- Reaffirms ADR-013: **DERIVED** findings → ML features; **DIAGNOSED/LEARNED** →
  labels/outputs, never fed back as features (circularity).

## 11. LLM interaction

The LLM consumes **only** the Knowledge Graph, `DIAGNOSED` findings (with their
self-contained firing rationale), evidence (artifact refs), and maintenance
recommendations — **never raw telemetry**. It traverses
`DIAGNOSED finding → TRIGGERED_BY → DERIVED findings → Evidence` and
`FindingCondition → INDICATES → FaultMechanism → MANIFESTS_AS → FailureMode →
MITIGATED_BY → MaintenanceAction`, answering *"why is condenser fouling
suspected on SC-126?"* by **reading** the diagnosis rationale and citing rule/
finding/artifact ids. Read-only, grounded, no recomputation (ADR-009).

## 12. Rule ontology (KG additions — activates ADR-014 §10)

```
NODES (new)
  EngineeringRule    { rule_id, version, kind, scope, priority, description }
  FaultMechanism     { key, name, description }      # e.g. condenser_fouling
  FailureMode        { key, name, description }      # e.g. high_pressure_trip
  MaintenanceAction  { key, description }            # e.g. clean_condenser

EDGES (new)
  EngineeringRule   -PRODUCES->     FindingCondition(DIAGNOSED)
  FindingCondition(DIAGNOSED) -TRIGGERED_BY-> FindingCondition(DERIVED)   # reasoning chain
  FindingCondition  -INDICATES->    FaultMechanism    { confidence, provenance }
  FaultMechanism    -MANIFESTS_AS-> FailureMode
  FailureMode       -MITIGATED_BY-> MaintenanceAction
  FindingCondition  -RECOMMENDS->   MaintenanceAction
  FindingCondition  -SUPPRESSES->   FindingCondition  { reason }           # monotonic annotation
  FindingCondition  -PRECEDES->     FindingCondition  { confidence }        # learned (ML)
```

## 13. Example reasoning chains — SC-126 (honest)

SC-126 is genuinely healthy, so two of these are illustrative and one is real —
labeled as such.

**(a) REAL — Suppression / configuration diagnosis (fires on SC-126 today):**
```
DERIVED: THRESHOLD_MISSPECIFIED@discharge_pressure (typ. op below band)
DERIVED: (no protection breach)  +  Health OK  +  no HEALTH_DEGRADED
   └─ Rule R-THR-CONFIG (kind=SUPPRESSION+MAINTENANCE, scope=EQUIPMENT_CLASS)
      → DIAGNOSED: THRESHOLD_CONFIG_REVIEW_RECOMMENDED (severity=info)
        -SUPPRESSES-> the "looks-like-a-fault" reading of the threshold breach
        -RECOMMENDS-> MaintenanceAction(review_discharge_pressure_setpoints)
      confidence high (99% coverage), reliability_factor 1.0.
```
This is the correct, honest SC-126 conclusion: *not a fault — a setpoint config
issue.*

**(b) ILLUSTRATIVE — Diagnostic chain (does NOT fire on SC-126; healthy):**
```
IF  HIGH_DISCHARGE_TEMP  +  HIGH_CONDENSER_ENTERING_TEMP
    +  RISING_DISCHARGE_PRESSURE  +  RUNTIME_CONTINUOUS_FULL_LOAD
THEN Rule R-COND-FOUL (kind=DIAGNOSTIC, scope=EQUIPMENT_CLASS)
   → DIAGNOSED: CONDENSER_FOULING_SUSPECTED (warning)
     -INDICATES-> FaultMechanism(condenser_fouling)
                  -MANIFESTS_AS-> FailureMode(high_pressure_trip)
                  -MITIGATED_BY-> MaintenanceAction(clean_condenser)
```

**(c) ILLUSTRATIVE — Reliability-gated (shows the trust discount):**
```
Same antecedent as (b), BUT condenser_entering_temp has RELIABILITY_DRIFT
   → reliability_factor < 1  → CONDENSER_FOULING_SUSPECTED emitted at REDUCED
     confidence, detail: "diagnosis uncertain — condenser temp sensor drifting;
     verify sensor before acting."
```

## 14. Decision & next step

Adopt: reasoning-only responsibility (§1); the multi-signal rule boundary (§2);
`RuleKind × RuleScope` taxonomy (§3); the immutable, execution-state-free rule
contract with a reliability-discounted confidence model (§4); **monotonic
forward-chaining to a fixpoint with acyclic-dependency + idempotent-identity
termination** (§5); the `(priority, confidence, severity, rule_id)` total-order
conflict resolution with priority-over-confidence (§6); read-mostly / append-
only graph writes via the shared projector (§7); self-contained explainability
with backward-chained "why-not" (§8); the §12 ontology activating the fault-
mechanism/failure-mode nodes.

**Awaiting approval.** Next implementation unit would be the immutable
`RuleDefinition` contract + a small curated rule set (starting with the real
SC-126 threshold-config rule) + the deterministic monotonic evaluator writing
DIAGNOSED findings through the existing projector — with behaviour, contract,
determinism, conflict-resolution, and SC-126 reasoning-chain tests. No ML, no
LLM yet.

## 15. Accepted refinements (owner review, 2026-07-10)

**R1 — Persist the reasoning chain (not reconstructed later).** Every DIAGNOSED
finding carries an explicit, immutable `triggered_by` list of the *finding
identities* that fired the rule; the projector materialises these as
`TRIGGERED_BY` edges (DIAGNOSED condition → trigger condition). The chain
`diagnosis → triggers → evidence` is therefore **queryable and auditable in the
graph**, never re-derived by the LLM.

**R2 — Diagnosis confidence is a documented composition.** Deterministic and
explainable:
```
diagnosis_confidence = rule_confidence
                     × evidence_confidence          # mean confidence of the required triggers
                     × reliability_factor           # min trust of the sensors involved (<=1)
```
clamped to [0, 1]. The `Confidence.rationale` records all three inputs, so a
diagnosis resting on a drifting sensor is visibly discounted and self-explaining.

**R3 — Validation rules (new taxonomy kind).** `RuleKind.VALIDATION` rules
reason about the **platform's own consistency**, not the equipment: missing
evidence, contradictory deterministic outputs (e.g. a CRITICAL alarm resting on
a `SENSOR_UNTRUSTWORTHY` sensor), configuration inconsistencies, incomplete
knowledge-graph coverage. They emit `category=VALIDATION` DIAGNOSED findings so
platform-integrity issues are surfaced through the same uniform contract as
engineering diagnoses, but are cleanly separable from them.
