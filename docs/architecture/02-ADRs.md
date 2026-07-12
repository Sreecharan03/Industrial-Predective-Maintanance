# SenseMinds 360 — Architecture Decision Records

Format per ADR: Context → Decision → Rejected alternatives → Consequences.

**Status: ACCEPTED (2026-07-10).** Approved with these owner decisions:
- **Scale:** single plant now → embedded KG + modular monolith (ADR-005, ADR-010).
- **ML:** three-phase model — **A** Deterministic (now) → **B** Pattern Learning
  (unsupervised, label-free) → **C** Supervised (needs labels). See revised
  ADR-007. Only Phase A is built now.
- **First build:** Foundation + ingestion refactor, Milestones 0–1 (see roadmap).

---

## ADR-001 — Deterministic core; agents only at the reasoning boundary

**Context.** The brief proposes ~14 LLM agents, roughly one per pipeline stage
(Data Acquisition Agent, Validation Agent, Sensor Mapping Agent, Threshold
Agent, Statistics-adjacent agents, …). Stages 1–11 of that list are
*deterministic transforms already implemented in pandas* (steps 1–12).

**Decision.** Keep every deterministic transform as plain, typed, tested
Python services ("engines"). Introduce agentic behaviour **only** where the
task is genuinely open-ended reasoning over ambiguous evidence:
(a) the **Diagnosis/Engineering-Intelligence** agent, (b) the **LLM Reasoning
/ Narrative** agent, and (c) an **Orchestration** agent that sequences those
when a human asks an open question ("why is SC-114 Com2 running warm?").
Everything else is a function call, not an agent.

**Rejected alternatives.**
- *Agent-per-stage (as briefed).* Rejected: wrapping `df.groupby()` in an LLM
  agent adds latency, token cost, nondeterminism, and hallucination surface
  for zero analytical gain. It also makes results irreproducible — fatal for
  an industrial audit trail.
- *No agents at all (pure rules).* Rejected: the open-ended "explain/diagnose
  in engineer's language across correlated evidence" task genuinely benefits
  from LLM reasoning, provided it is grounded (ADR-009).

**Consequences.** Reproducible, cheap, fast core. LLM spend and failure modes
are confined to a small, well-guarded surface. "Agentic platform" is true
where it matters and false where it would only add risk.

---

## ADR-002 — Orchestration: typed DAG / Prefect for deterministic work, LangGraph inside the reasoning node

**Context.** The brief asks to choose CrewAI *or* LangGraph as the backbone,
on suitability not popularity.

**Decision.** Two-tier orchestration.
1. **Deterministic pipeline** (ingestion → quality → engines → KG → rules →
   health): a plain typed DAG executor. Start with a lightweight in-process
   DAG; adopt **Prefect** when scheduling, retries, and backfills across many
   assets justify it. This work is a data pipeline and wants a data-pipeline
   orchestrator, not an agent framework.
2. **Reasoning workflow** (diagnosis, human-in-the-loop Q&A, narrative):
   **LangGraph** — because it gives explicit, inspectable state machines,
   durable/resumable runs, controllable branching, and first-class
   human-in-the-loop interrupts, which match an industrial, auditable context.

**Rejected alternatives.**
- *CrewAI as backbone.* Rejected: its role-playing "crew" abstraction optimizes
  for autonomous multi-agent collaboration, which is the opposite of what a
  deterministic, auditable industrial pipeline wants. Weaker explicit-state and
  durability story than LangGraph for long-running, resumable workflows.
- *One framework for everything.* Rejected: forcing deterministic ETL through
  an agent framework (or forcing reasoning through a DAG scheduler) is a
  category error. Use each tool for its shape of problem.

**Consequences.** Slightly more than one dependency, but each layer uses a
tool fit for purpose. The 90% deterministic surface never pays agent-framework
overhead.

---

## ADR-003 — The platform flow is a DAG, not a mandatory linear chain

**Context.** The brief mandates "every layer must consume outputs from the
previous layer," drawn as a 16-node line ending
`…Health → ML → LLM → Dashboard`.

**Decision.** Model dependencies as the actual DAG (see HLD §2). In particular:
Statistics/Threshold/State/Reliability run in **parallel** off validated data;
Envelope and Runtime depend on State, not on Statistics; Health depends on
Rules+Reliability+Envelope but **not** on ML; the LLM consumes KG+Rules+Health
(+ML when it exists) in parallel.

**Rejected alternatives.**
- *Strict linear chain (as briefed).* Rejected on two grounds: (1) it is
  factually wrong about dependencies (health does not need ML; envelope does
  not need threshold results); (2) it manufactures coupling and a critical
  path that the stated Clean-Architecture/SOLID goals explicitly forbid. A
  linear "must" contradicts the "no coupling" principle in the same brief.

**Consequences.** Parallelism where the data allows it; no artificial critical
path through ML; health and diagnostics are available before ML is ever built.

---

## ADR-004 — Reuse and refactor steps 1–12 as the engine layer; artifacts are the contracts

**Context.** A working analytics core already exists as scripts + CSV outputs.
The brief says "never duplicate their logic; reuse reports as foundational
knowledge."

**Decision.** Refactor `step*.py` + `common.py` into `engines/` packages with
typed inputs/outputs (Pydantic v2). Persist each engine's **typed result** to
an artifact store with provenance. Downstream layers consume these result
objects — *that* is the reuse mechanism. The markdown reports become a
rendering of these objects, not a source of truth.

**Rejected alternatives.**
- *Treat markdown reports as the knowledge source.* Rejected: prose is not a
  contract; parsing it back is fragile and lossy.
- *Rewrite the analytics from scratch under the new architecture.* Rejected:
  the logic is validated and non-trivial (density-valley state segmentation,
  dwell-time accounting, fault-code detection). Rebuilding invites regressions
  for no benefit.

**Consequences.** Fast path to a real platform; existing validation carries
forward; a clean typed boundary replaces CSV-by-convention.

---

## ADR-005 — Knowledge Graph: embedded first, Neo4j when multi-plant scale demands

**Context.** The KG is central to explainable reasoning. Scope today is 6 units
at one plant; the stated ambition is many plants.

**Decision.** Define one `KnowledgeGraphRepository` interface. Implement it
first with an **embedded, persisted graph** (typed schema over
NetworkX/SQLite-backed storage) — trivial to run in a studio, versionable,
zero ops. Swap in **Neo4j** behind the same interface when cross-plant scale,
concurrent writers, or graph-query complexity justify the operational cost.

**Rejected alternatives.**
- *Neo4j from day one.* Rejected: premature ops burden for a 6-unit graph;
  slows local iteration.
- *No interface, hard-code the store.* Rejected: guarantees a painful rewrite
  at the multi-plant transition.

**Consequences.** Cheap now, clean migration later, no lock-in.

---

## ADR-006 — Rule Engine before ML; deterministic, explainable, evidence-linked

**Context.** The highest-value, most-explainable diagnostics (e.g. high current
+ high discharge temp + high condenser temp → possible condenser fouling) are
**rules**, not models, and need no labels.

**Decision.** Build a deterministic rule engine now. Rules are declarative
(condition over engine outputs → candidate `FailureMode` with confidence),
versioned, and each firing produces a `Finding` linked to the exact `Evidence`
that triggered it. Include explicit **conflict resolution** (priority +
specificity) and **confidence scoring** (rule prior × evidence strength).

**Rejected alternatives.**
- *ML-first diagnostics.* Rejected: no failure labels exist (ADR-007), and ML
  diagnostics are far harder to make auditable than rules.
- *Free-form LLM diagnosis.* Rejected as the *source* of findings: not
  reproducible or auditable. The LLM explains rule findings; it does not
  originate them.

**Consequences.** Delivers the bulk of diagnostic value immediately with full
traceability; becomes the labeled-signal generator that may later bootstrap ML.

---

## ADR-007 — Three-phase ML model (Deterministic → Pattern Learning → Supervised)

**Revised 2026-07-10.** The earlier form of this ADR said "no ML until failure
labels exist." That was too restrictive and is corrected here: it conflated
*predictive maintenance* (which needs labels) with *all ML* (which does not).
Unsupervised learning and forecasting are legitimately label-free.

**Context.** The data: ~227k rows at 30-min irregular cadence, multi-week
logging gaps, fault-code contamination, and **no recorded failure events,
work orders, or RUL labels**. This constrains *which* ML is defensible, not
whether any ML is.

**Decision.** Adopt a three-phase model. Build strictly in order; each phase
is independently valuable.

- **Phase A — Deterministic Intelligence (building now).** Thresholds, states,
  envelope, runtime, reliability, knowledge graph, rules, health. Engineering
  logic over historical behaviour. Fully explainable/auditable. Milestones 1–5.
- **Phase B — Pattern Learning (unsupervised, label-free; designed-for, built
  after A).** Operating-state clustering (GMM/HDBSCAN) as an *enrichment* of the
  deterministic states, behavioural embeddings, similarity search, forecasting
  (power/discharge-temp/oil-temp/pressure), and unsupervised novelty scoring.
  Three guardrails: (1) novelty is framed as **"unlike history," never
  "fault"**, and ships as an advisory signal *behind* the deterministic rules,
  because without labels its false-positive rate cannot be measured; (2) it is
  an **enrichment** of Phase A, never a replacement — the deterministic "why"
  is never lost; (3) forecasting must handle the irregular cadence + gaps and
  be tied to a decision (lead time before a threshold breach), not produced for
  its own sake.
- **Phase C — Supervised ML (needs labels).** Failure classification, RUL,
  maintenance optimization, failure prediction. Built only once a labeled event
  log exists.

**The label-bootstrap loop.** Phase B is designed to *generate* Phase C's
labels: when an engineer triages a Phase-B novelty signal ("was this real?"),
that judgment is captured as a label. Phase B therefore both adds value now
*and* unlocks Phase C, instead of the two being disconnected.

**Architecture placement.** Health Score fans out to **Pattern Learning
(unsupervised)** and **Supervised ML (labeled)** in parallel; both feed the LLM
reasoning node as additional evidence inputs (see HLD §2). Neither gates health
or the rule engine.

**Rejected alternatives.**
- *Train supervised PdM models now.* Rejected: no labels → unvalidatable,
  unsafe to surface in a pharma utility.
- *"No ML at all until labels" (the prior form of this ADR).* Rejected: it
  needlessly forbids label-free unsupervised learning and forecasting that can
  add value today and seed the labels Phase C needs.
- *Unsupervised anomaly detection as a primary alarm.* Rejected: an unmeasured
  false-positive rate makes it untrustworthy as a standalone alarm; advisory
  only.

**Consequences.** The platform is useful and honest at every phase: Phase A
explains, Phase B discovers patterns and harvests labels (making no failure
claims), Phase C predicts once it can be validated.

---

## ADR-008 — Health scoring is deterministic, hierarchical, and explainable

**Context.** The brief wants sensor→subsystem→equipment→plant health, with
explainable weighting, and (in the linear chain) placed after ML.

**Decision.** Health is a **deterministic aggregation**, independent of ML:
sensor health from reliability + envelope-excursion + threshold-validation
signals; subsystem/equipment/plant health from weighted rollups whose weights
are declared in config and rendered in every explanation. Each score exposes
its contributing factors and the evidence IDs behind them.

**Rejected alternatives.**
- *ML-derived health index.* Rejected: opaque and label-dependent; unsuitable
  as the platform's primary trust signal.
- *Flat single score.* Rejected: hides where a problem lives; the hierarchy is
  the diagnostic value.

**Consequences.** A trustworthy, day-one health signal that a maintenance
engineer can interrogate down to the sensor.

---

## ADR-009 — LLM is a constrained narrator over structured evidence

**Context.** Industrial recommendations must be traceable; hallucination is a
safety issue.

**Decision.** The LLM Reasoning node may only select, order, and explain
existing structured evidence (KG facts, rule `Findings`, health scores,
engine results). It must cite artifact/finding IDs for every claim, must never
compute numbers or invent thresholds, and must return "insufficient evidence"
when evidence is absent. Enforced by grounding the prompt in retrieved
structured context and validating outputs against cited IDs.

**Rejected alternatives.**
- *LLM computes/estimates values.* Rejected: unverifiable, unsafe.
- *LLM as autonomous decision-maker.* Rejected: human-in-the-loop is required
  for any action recommendation (LangGraph interrupt, ADR-002).

**Consequences.** Natural-language explanations with zero fabricated facts;
every sentence is auditable back to a computed artifact.

---

## ADR-010 — Modular monolith first, not microservices

**Context.** The brief's ~30-package layout is microservice-shaped. Current
reality: one developer, one studio, one plant.

**Decision.** Ship a **modular monolith**: one deployable, strict internal
module boundaries (the layers of HLD §3), one FastAPI app, one config system.
Extract a module into its own service only when a concrete scaling or team
boundary demands it. Keep the package structure clean enough that extraction is
mechanical.

**Rejected alternatives.**
- *Microservices from day one (as the layout implies).* Rejected: distributed-
  systems tax (network failures, partial deploys, cross-service tracing,
  eventual consistency) with none of the benefits at current scale.
- *Unstructured monolith.* Rejected: gives up the clean boundaries that make
  later extraction possible.

**Consequences.** Fast iteration now; a credible path to services later without
a rewrite.
