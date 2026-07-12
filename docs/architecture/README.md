# SenseMinds 360 — Architecture Specification (v1)

Owner role: Chief Software Architect / Principal AI + Industrial IoT Engineer.
Status: **Draft for approval.** No platform code is written until the ADRs
below are accepted or amended.

This specification deliberately **does not** rubber-stamp the requested
architecture. Several requested decisions are rejected here with
justification and a better alternative proposed, because that is the job the
architect was hired to do.

## Read in this order

1. **[01-HLD.md](01-HLD.md)** — High-Level Design. The corrected component
   model and data flow (a DAG, not the mandated 16-step linear chain), the
   layered boundaries, inter-layer data contracts, and where the platform
   reuses the already-built Phase-1/2 engines instead of rebuilding them.
2. **[02-ADRs.md](02-ADRs.md)** — Architecture Decision Records. Ten
   decisions, each with context, the decision, **rejected alternatives**
   (including several from the original brief), and consequences. This is the
   document to argue with.
3. **[03-build-roadmap.md](03-build-roadmap.md)** — the module-by-module
   build order, what "done" means per module, and what is explicitly
   deferred (with the trigger condition that would un-defer it).

## The five challenges to the original brief (summary)

| # | Requested | Verdict | Corrected position (see ADR) |
|---|---|---|---|
| 1 | "Every layer must consume the previous layer" — a 16-step linear pipeline | **Reject** | It is a **DAG**. Forcing linearity manufactures the coupling Clean Architecture forbids. (ADR-003) |
| 2 | ~14 LLM agents, one per pipeline stage | **Reject** | Deterministic transforms must stay deterministic Python. Agents only at the **reasoning boundary** (diagnosis, narrative, orchestration of ambiguous work). (ADR-001) |
| 3 | CrewAI *or* LangGraph as the platform backbone | **Reject the framing** | Backbone = plain typed DAG / Prefect for deterministic work; **LangGraph only inside the reasoning node**. CrewAI rejected as backbone. (ADR-002) |
| 4 | Full ML training layer now | **Defer** | The dataset has **no failure labels** and sparse event density. Build the feature **contract** now; train models when labeled events exist. (ADR-007) |
| 5 | 30-package enterprise scaffold, microservice-shaped | **Reduce** | **Modular monolith** first, refactoring the existing steps 1–12 into typed packages. Split to services only when scale demands. (ADR-004, ADR-010) |

The vision itself — an explainable, traceable, evidence-referenced industrial
intelligence platform that reasons like a maintenance engineer — is accepted
in full. The disagreement is purely about **how much machinery** that vision
actually requires, and in what order.
