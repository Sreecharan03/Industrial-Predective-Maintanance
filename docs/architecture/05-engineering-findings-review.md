# ADR-012 — Engineering Findings Layer (before the Knowledge Graph)

Status: **ACCEPTED (2026-07-10).** Owner approved Option B and the re-ordering
**Engineering Findings layer → Knowledge Graph → Rule Engine**. Implementation
of the Findings layer is the next milestone (awaiting go-ahead to begin).

## Question

Should an intermediate **Engineering Findings** layer exist between the
deterministic analytics engines and the Knowledge Graph? And should the KG
consume **engine outputs directly** or **standardized Engineering Findings**?

## Context

The deterministic core now emits seven heterogeneous typed results
(Statistics, State, Envelope, Threshold, Timeline, Reliability, Health). The
KG's purpose is to store *validated engineering knowledge* that the Rule
Engine and LLM reason over. The `Finding` domain entity already exists
(summary + severity + confidence + evidence[] + provenance) and the Rule
Engine is already specified to produce `Finding`s.

## Options

- **A — KG consumes engine results directly.** The graph ingests
  `ThresholdResult`, `HealthResult`, etc. and stores them as evidence nodes.
- **B — KG consumes standardized `Finding`s.** An Engineering Findings layer
  normalizes engine outputs into uniform `Finding`s; the KG consumes those.

## Decision — **B: introduce the Engineering Findings layer; the KG consumes Findings, not raw engine outputs.**

Reasoning:

1. **"Knowledge, not raw data" — the stated goal.** A raw engine result is a
   *computation* (percentiles, breach counts, a score). A `Finding` is a
   *validated engineering statement* — "SC-126 discharge-pressure threshold is
   mis-specified: typical operation (199-221) sits below the operating band" —
   carrying severity, confidence, and evidence. The Findings layer is exactly
   the raw-data→knowledge boundary the KG should sit behind.
2. **One uniform contract for the reasoning tier.** The KG, Rule Engine, and
   LLM should all speak one language. If the KG consumed seven result schemas
   it would couple to every engine; consuming `Finding` couples it to one
   stable contract. The Rule Engine already produces `Finding`s, so KG + Rules
   align on the same currency.
3. **Decoupling / maintainability.** When an engine's result schema evolves,
   only its finding-derivation adapter changes — not the KG, the Rule Engine,
   or the LLM prompt. This is the highest-leverage seam in the platform.
4. **Lean graph, full detail retained.** Each `Finding` references its source
   artifact id(s) as evidence. The KG stores compact validated statements; the
   full result stays in the artifact store, retrievable by id. The KG never
   holds raw time-series.
5. **LLM grounding.** The LLM reasons over uniform, cited, confidence-scored
   `Finding`s — not over raw result objects — which is the anti-hallucination
   posture from ADR-009.

### Scope of the Findings layer (important)

The Findings layer produces **two categories** of `Finding`, both uniform:

- **Direct engine verdicts** (deterministic, one engine → finding): e.g.
  "threshold mis-specified" (from Threshold + Envelope), "sensor untrustworthy:
  drift" (from Reliability), "condenser subsystem degraded" (from Health). These
  are near-mechanical derivations from a single engine's verdict.
- **Diagnostic findings** (multi-signal inference): produced by the **Rule
  Engine** — e.g. "possible condenser fouling" from high discharge temp + high
  condenser temp + rising discharge pressure. These correlate several engines.

So the Rule Engine is a *producer* of `Finding`s, and the Findings layer is the
*superset* that also standardizes direct engine verdicts. Both feed the KG.

### What the KG still gets from elsewhere

The KG holds two kinds of content: **structure** (equipment ↔ subsystem ↔
sensor ↔ threshold ↔ failure-mode taxonomy) — seeded from the **catalog**, not
from findings — and **dynamic knowledge** (findings/evidence attached to those
nodes). Findings populate the latter; the catalog seeds the former.

## Consequence for sequencing (updates ADR-011)

ADR-011 ordered "KG → Rule Engine". This ADR inserts the Findings layer and
re-orders the tail:

> **Engineering Findings layer → Knowledge Graph → Rule Engine**

- Build the **Findings contract + a first Findings assembler** (deriving
  direct-verdict findings from Threshold, Health, Reliability) first, so the KG
  has validated knowledge to store from day one.
- The **KG** consumes `Finding`s (+ catalog structure).
- The **Rule Engine** then adds diagnostic `Finding`s, which flow through the
  same assembler contract into the KG.

## Recommendation to the owner

Approve Option B and the re-ordering. Next implementation unit would be the
**Engineering Findings layer** (contract + deterministic assembler over the
existing engine verdicts), *then* the Knowledge Graph. This keeps the KG a
store of validated engineering knowledge, exactly as intended.

**Awaiting approval before implementing the Knowledge Graph (or the Findings
layer).**
