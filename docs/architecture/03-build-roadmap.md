# SenseMinds 360 — Build Roadmap

Principle: build in dependency order, each module production-quality (typed,
validated, logged, tested) before the next. No placeholders, no TODOs, no
pseudo-code — but also no attempt to emit the whole platform in one pass. Each
milestone is independently useful and independently reviewable.

## Milestone 0 — Foundation (project skeleton + contracts)
- `senseminds/` modular-monolith package; `pyproject.toml`, ruff/black,
  pre-commit, pytest, Pydantic v2 settings, structured logging + tracing base.
- `domain/` entities & value objects (Asset, Sensor, Reading, OperatingState,
  Threshold, Envelope, FailureMode, Rule, Finding, Evidence, HealthScore).
- Artifact store interface + local implementation (typed result + provenance).
- **Done when:** domain types + artifact store are tested; empty app boots.

## Milestone 1 — Ingestion + Data Engineering + Quality gate
- Refactor `extract_pdfs.py` and `step1/step5` into `engines/ingestion` and
  `engines/quality`. Quality gate as a cross-cutting validator (ADR-003).
- Edge cases wired in from the start: missing/duplicate timestamps, clock
  drift, timezone normalization, frozen/oscillating sensors, fault-code values
  (-99.9/-49.5/-110.0), negative-pressure zero-offset, partial/corrupt files,
  logging-gap detection.
- **Done when:** the 6 existing units re-ingest to validated typed series with
  a quality report that matches the current Phase-1 numbers (regression guard).

## Milestone 2 — Deterministic engines (refactor of steps 2,3,4,6,8,9,11)
- One package per engine, each a stateless service: Sensor Mapping, Threshold,
  Statistics, Operating State, Operating Envelope, Runtime, Reliability.
- Each emits a versioned typed result; parity-tested against current CSV
  outputs so the refactor is provably behaviour-preserving.
- **Done when:** engine outputs reproduce Phase-1/2 artifacts within tolerance.

## Milestone 3 — Knowledge Graph
- `KnowledgeGraphRepository` interface + embedded implementation (ADR-005).
- Seed equipment taxonomy + sensor mapping; attach engine results as evidence.
- **Done when:** graph answers "which sensors/states/thresholds relate to asset
  X" and returns evidence IDs.

## Milestone 4 — Rule Engine + Health Scoring
- Declarative rules over engine outputs → `Finding`s with evidence + confidence;
  conflict resolution + prioritization (ADR-006).
- Deterministic hierarchical health (ADR-008).
- Seed rules from `step7`/`step12` engineering insights + refrigeration domain
  (e.g. condenser-fouling, oil-system, load-imbalance signatures).
- **Done when:** each asset yields explainable findings + a drill-down health
  tree, every claim linked to evidence.

## Milestone 5 — API + Dashboard (BFF)
- FastAPI over the use-cases; read models for the dashboard; auth/z; metrics.
- **Done when:** an engineer can browse asset → health → findings → evidence.

## Milestone 6 — LLM Reasoning node (LangGraph)
- Constrained narrator (ADR-009) with human-in-the-loop interrupts (ADR-002).
- **Done when:** open questions get grounded, cited, "insufficient-evidence"-
  safe answers.

## ML — three-phase model (ADR-007)
- **Phase A (now):** the deterministic engines of Milestones 1–5. No ML.
- **Phase B (after A; unsupervised, label-free):** feature contract + feature
  pipeline first, then operating-state clustering (enrichment of the
  deterministic states), behavioural embeddings, forecasting, and advisory
  novelty scoring. Ships behind the rules; frames novelty as "unlike history,"
  never "fault"; designed to harvest labels via engineer triage.
- **Phase C (trigger: labeled events exist):** supervised failure
  classification, RUL, maintenance optimization, behind the ML-layer interface.

## Cross-cutting, every milestone
Input/output validation · structured logging · metrics · tracing · retries &
timeouts on all I/O · config validation · graceful shutdown · concurrency
safety · resource cleanup · unit + integration + contract tests · error
propagation with typed exceptions.

## What I need before Milestone 0
The three approval questions in the accompanying message. They change the KG
store, the ML posture, and the first module built — so they are worth settling
before any package is created.
