# ADR-014 — Knowledge Graph: Architecture Review (M4)

Status: **Proposed** (2026-07-10). Defines the semantic boundary and ontology
of the Knowledge Graph. **No implementation.** Builds on ADR-012/013.

## 0. The one principle everything follows

> The graph stores **engineering knowledge and relationships**, never
> **telemetry or derived numbers.**

Where 90% of industrial-AI graphs fail is by turning the graph into a
time-series store (`Sensor → Value → Time`). That is what the artifact store
and a future time-series DB are for. Our graph holds:
`Equipment → Subsystem → Sensor → Finding → Rule → FailureMode`.

## 1. The boundary — permanent knowledge vs transient observation

| Store **forever** (graph) | **Never** in the graph (artifact store / TSDB) |
|---|---|
| Plant, Area, Equipment, Subsystem, Sensor | Individual sensor readings |
| Threshold *definitions* | Statistics, percentiles, histograms |
| Engineering Rules | Health *scores* (the numbers) |
| Failure Modes, Maintenance Actions | Current values, runtime calculations |
| **Persistent Finding-conditions** | Timeline samples/events |
| Relationships (structural, evidential, causal) | Any raw or derived value |

Everything on the right is **derived**, not knowledge; the graph references it
by `artifact_id` through evidence, but never stores the value.

## 2. The crux — a graph node is a CONDITION, not an OBSERVATION

The single most important decision: **the graph node is the `identity_key`
(the condition "X on asset A"), not the per-run `finding_id` (an observation).**

- Each pipeline run emits `finding_id` observations (transient, immutable,
  live in the findings/artifact store).
- The graph holds one **`FindingCondition` node per `identity_key`**, carrying
  lifecycle metadata: `first_seen`, `last_seen`, `occurrences`,
  `latest_severity`, `latest_finding_id`, `status`. Observations **update** this
  node's metadata; they are **not** individual nodes.

This is what stops the graph becoming telemetry: 100 runs of the same condition
= **one** node with `occurrences=100`, not 100 nodes.

### Which Findings persist / expire
- **Persist as a node:** WARNING/CRITICAL conditions, anything linked to a
  FailureMode or MaintenanceAction, and any recurring condition
  (`occurrences ≥ k`). These are engineering knowledge.
- **Do not promote / prune:** one-off INFO conditions that never recur — noise,
  kept only in the transient findings store.
- **Expire → HISTORICAL (not deleted):** a condition not re-derived for a
  retention window becomes `status = historical`. It is **retained** (not
  deleted) if it is WARNING+/failure-linked, because "which findings preceded a
  failure" is exactly the query the graph must answer years later. Only
  unlinked INFO noise is truly pruned.

## 3. Evidence linking

Evidence is a **reference edge**, never data. `FindingCondition
─HAS_EVIDENCE→ Artifact(ref)` where the edge/property carries
`artifact_id + observed_value` (inlined summary for self-containment) and points
at the engine result in the artifact store. The graph stores the *link and the
one summary value*, not the artifact contents — so the LLM can cite and drill
down without the graph holding telemetry.

## 4. Specific answers

- **Should Health become a graph node?** The health **score** — **no** (derived
  number). A `HEALTH_DEGRADED` **finding-condition** — **yes** (knowledge).
- **Should Timeline events become graph nodes?** Individual events/samples —
  **no** (telemetry). A `RUNTIME_*` finding derived from the timeline
  (e.g. "operates continuously at full load") — **yes**, as a finding-condition.
- **Engineering vs causal edges — both, typed distinctly:**
  - **Structural** (deterministic, static): `HAS_SUBSYSTEM`, `HAS_SENSOR`,
    `GOVERNED_BY`, `MEASURES`, `PART_OF`.
  - **Evidential** (deterministic): `OBSERVED_ON`, `HAS_EVIDENCE`, `SUPERSEDES`.
  - **Causal / diagnostic** (inferred, **confidence-scored, provenance-carrying**):
    `INDICATES` (finding→failure mode), `PRECEDES` (finding→finding, learned),
    `CAUSES` (failure→failure), `MITIGATED_BY` (failure→action).
  Structural/evidential edges are facts; causal edges are **claims** and must
  carry confidence + provenance. Keeping them distinct is what prevents the
  graph from asserting hypotheses as facts.

## 5. Ontology

```
NODES
  Plant, Area
  Equipment(Asset)     { key, equipment_class, description }
  Subsystem            { key, name }
  Sensor               { key, sensor_type, unit }
  ThresholdDefinition  { sensor_key, operating[min,max], protection[], status }
  FindingCondition     { identity_key, finding_type, category, scope, target_key,
                         latest_severity, first_seen, last_seen, occurrences,
                         status(active|historical), latest_finding_id, confidence }
  FailureMode          { key, name, description }
  EngineeringRule      { rule_id, description, priority }
  MaintenanceAction    { key, description }
  ArtifactRef          { artifact_id }              # reference only, no values

EDGES
  Plant       -HAS_AREA->        Area
  Area        -HAS_EQUIPMENT->   Equipment
  Equipment   -HAS_SUBSYSTEM->   Subsystem
  Subsystem   -HAS_SENSOR->      Sensor
  Sensor      -GOVERNED_BY->     ThresholdDefinition
  FindingCondition -OBSERVED_ON-> (Sensor|Subsystem|Equipment)
  FindingCondition -HAS_EVIDENCE-> ArtifactRef      { observed_value }
  FindingCondition -SUPERSEDES->  FindingCondition
  FindingCondition -INDICATES->   FailureMode        { confidence, provenance }
  EngineeringRule  -CONCLUDES->   FailureMode
  EngineeringRule  -PRODUCES->    FindingCondition   (DIAGNOSED)
  FailureMode -MITIGATED_BY->     MaintenanceAction
  FailureMode -CAUSES->           FailureMode        { confidence }
  FindingCondition -PRECEDES->    FindingCondition   { confidence, support }  # learned
```

## 6. Example subgraphs

**(a) Structure — permanent, from the catalog**
```
(SC-126:Equipment)-HAS_SUBSYSTEM->(compression:Subsystem)-HAS_SENSOR->(discharge_pressure:Sensor)
                                                                         -GOVERNED_BY->(td:ThresholdDefinition 235-247 +prot)
```

**(b) Finding knowledge — from the Findings layer (real SC-126)**
```
(SC-126)-HAS_SUBSYSTEM->(compression)-HAS_SENSOR->(discharge_pressure)
                                                          ^
                                                          | OBSERVED_ON
(FindingCondition THRESHOLD_MISSPECIFIED, occurrences=1, severity=warning)
   -HAS_EVIDENCE->(ArtifactRef SC-126__threshold){observed_value: 94.87%}
```

**(c) Diagnostic + causal — future (Rule Engine + curated knowledge)**
```
(FC HEALTH_DEGRADED@condenser)  ┐
(FC RELIABILITY_DRIFT@cond_temp)├─(Rule R-COND-FOUL)-PRODUCES->(FC DIAGNOSTIC condenser_fouling)
(FC THRESHOLD rising discharge) ┘                                -INDICATES->(FailureMode condenser_fouling){conf 0.7}
                                                                              -MITIGATED_BY->(clean_condenser)
```

## 7. How the consumers use the graph

- **Rule Engine** queries *structure + active FindingConditions* ("all active
  conditions on subsystem X"), fires rules, and writes back `DIAGNOSED`
  FindingConditions + `INDICATES` edges. It reasons over conditions, never
  telemetry.
- **Pattern Learning** consumes the graph as **engineering-level features**: per
  asset, the vector of active finding-conditions (type/severity/recurrence) and
  historical condition **sequences** — enabling features like *High Runtime →
  High Oil Temp → Low Reliability → Threshold Misconfigured* instead of raw
  signals. Per ADR-013: DERIVED conditions are features; DIAGNOSED/LEARNED are
  labels, never fed back as features.
- **LLM** traverses read-only: `Equipment → FindingCondition → Evidence(artifact)`
  and `FindingCondition → FailureMode → MaintenanceAction`. It answers *"which
  compressors have historically misconfigured thresholds?"* by matching
  `FindingCondition{type: THRESHOLD_MISSPECIFIED}` and citing evidence — never
  by reading a pressure value.

The graph answers **"which equipment has condition X / which conditions precede
failure Y"**, *not* "what's the pressure." That difference is the whole point.

## 8. Storage (reaffirms ADR-005)

Embedded graph behind a `KnowledgeGraphRepository` interface first (typed
schema over NetworkX/SQLite — versionable, zero-ops for one plant); Neo4j later
when multi-plant scale/concurrency justifies it. No lock-in.

## 9. Decision & next step

Adopt: the §1 boundary, the §2 *condition-not-observation* node rule, the §5
ontology, and the typed structural/evidential/causal edge separation. The graph
stores curated structure + engineering knowledge + persistent finding-conditions
+ relationships; never telemetry.

Next implementation unit is the `KnowledgeGraphRepository` interface + embedded
store + a **projector** that folds Findings into FindingCondition nodes/edges
(idempotent, deterministic) — seeded with catalog structure. No Rule Engine yet.

## 10. Accepted refinements (owner review, 2026-07-10)

**R1 — Projection idempotency is a core contract (mandatory).** Running
`KnowledgeGraphProjector` any number of times with identical inputs must yield
an *identical* graph state: no duplicate nodes, edges, or evidence links, and no
double-counted occurrences. The mechanism: a `FindingCondition` node records the
**set of distinct `finding_id`s** it has absorbed; `occurrences = |set|`, and
`first_seen / last_seen / latest_finding_id / latest_severity` are derived
**deterministically from the observed_window of those findings** (data-derived,
not wall-clock), so re-projecting a `finding_id` already in the set is a no-op.
Nodes are keyed by node id and edges by (src, dst, type) so upserts dedup by
construction. This is validated by dedicated idempotency tests (project once vs.
twice vs. N times ⇒ byte-identical graph).

**R2 — Fault Mechanism vs Failure Mode (documented future extension, not built
now).** The engineering model ultimately wants two distinct concepts:
`Finding → FaultMechanism (condenser fouling) → FailureMode (high-pressure
trip) → MaintenanceAction (clean condenser)`. A fault *mechanism* is the physical
degradation process; a failure *mode* is its functional manifestation. This
distinction is **not required for the current milestone** (no FailureMode nodes
are created until the Rule Engine + curated failure knowledge exist), so per the
"no unnecessary complexity now" rule it is **recorded here as a planned ontology
extension**: the future `FailureMode` node splits into `FaultMechanism` and
`FailureMode`, with edges `FindingCondition -INDICATES-> FaultMechanism
-MANIFESTS_AS-> FailureMode -MITIGATED_BY-> MaintenanceAction`. Nothing in the
current structural + FindingCondition projection depends on or pre-empts it.
