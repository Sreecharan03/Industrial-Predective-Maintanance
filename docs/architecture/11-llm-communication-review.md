# ADR-018 — LLM Communication Layer: Architecture Review (Final Layer)

Status: **PROPOSED (2026-07-12)** — awaiting approval. Builds on ADR-014
(Knowledge Graph), ADR-015 (Rule Engine), ADR-016 (Pattern Learning), ADR-017
(Forecasting), ADR-013 (Finding contract / origins). This is the **last
architectural layer**; after it, remaining work is dashboard, APIs, deployment,
and Phase C (supervised, once labels exist).

## 0. Context — the LLM is a *consumer*, not an engine

Every layer before this one **produces grounded evidence**: deterministic
analytics → engineering findings → knowledge graph → rule-based diagnoses →
learned/forecast hypotheses. The LLM adds **no new evidence.** It is a
**communication layer** that retrieves already-computed, already-attributed
evidence and renders it in natural language — for different audiences, at
different confidence registers, always with citations.

The single load-bearing principle: **the LLM may only restate what the stack
already decided.** If a statement is not backed by a retrieved Finding, Rule
firing, Pattern, or Forecast with an id, the LLM must not make it. This is not a
prompt-engineering nicety — it is enforced by a **grounding/citation framework**
that the generator physically cannot bypass, and by tests that fail the build if
it does.

## 1. Responsibility — a hard boundary

| The LLM IS responsible for | The LLM is NEVER responsible for |
|---|---|
| Explaining deterministic analytics (in words) | Recomputing analytics / re-deriving numbers |
| Explaining engineering findings | Creating deterministic findings |
| Explaining rule-based diagnoses | Overriding, re-running, or second-guessing the Rule Engine |
| Explaining learned hypotheses (novelty, regimes) | Inventing diagnoses or failure modes |
| Explaining forecast hypotheses | Reading raw telemetry to reason numerically |
| Generating structured engineering reports | Inventing maintenance recommendations |
| Answering natural-language questions over the evidence | Making autonomous decisions or executing actions |

The boundary is architectural, not advisory: the LLM's **only inputs** are the
retrieval outputs of §2. It has **no handle** to the analytics engines, the Rule
Engine's evaluator, or telemetry stores. It cannot call them because they are not
wired to it. What it cannot reach, it cannot corrupt.

## 2. Retrieval architecture — a curated evidence bundle, not a data lake

Retrieval assembles a typed, read-only **`EvidenceBundle`** from the existing
grounded stores, scoped to the question's asset(s)/time window:

- **Engineering Findings** (the Finding contract, ADR-013) — carrying origin
  (DERIVED / DIAGNOSED / LEARNED), category, severity, confidence, evidence,
  provenance, ids.
- **Knowledge Graph** — condition nodes, rule-diagnosis nodes, discovered
  patterns, learned-model nodes, and their edges (`TRIGGERED_BY`, `SUGGESTS`,
  `DISCOVERED_BY`, `PRECEDES`). The graph is the primary retrieval surface — it
  already encodes *condition, not observation*, and *fact vs. hypothesis*.
- **Rule Engine outputs** — fired rule instances with rule id, priority,
  reliability-discounted confidence, and the antecedent findings (the persisted
  reasoning, ADR-015).
- **Forecast hypotheses** — `FORECAST_THRESHOLD_APPROACH` findings + forecast
  pattern nodes (model, version, backtest coverage, lead time).
- **Pattern-learning hypotheses** — novelty / regime patterns + model health.
- **Artifact references** — ids/paths to the immutable analytic artifacts
  (EngineResults) that back a claim, for drill-down. **Referenced, not inlined.**

**Raw sensor streams are never retrieved for reasoning.** They are fetched
**only on explicit user request** ("show me the actual discharge-pressure trace
for Tuesday"), through a separate, clearly-labelled telemetry path, and even then
they are **presentation data for a chart, not reasoning input** — the LLM does
not compute over them. Default retrieval touches evidence, never telemetry.

## 3. Prompt assembly — preserve the epistemic categories

Evidence is assembled into the prompt in **five explicitly separated sections**,
never blended into one narrative soup:

1. **Engineering Facts** — DERIVED findings + deterministic analytics
   (thresholds, statistics, reliability). Certainty: measured/computed.
2. **Diagnosed Findings** — DIAGNOSED findings from fired rules. Certainty: rule
   confidence (composed, discounted).
3. **Learned Hypotheses** — LEARNED pattern findings (novelty, regimes).
   Certainty: pattern confidence + model health.
4. **Forecasts** — LEARNED forecast hypotheses. Certainty: forecast interval +
   backtest coverage.
5. **Unknown / Insufficient Evidence** — an explicit, first-class section listing
   what was asked but *not* supported by the bundle, so the model has an
   authorised place to say "not known" instead of inventing.

The prompt **instructs the model to keep these registers distinct in its output**
and the response schema (§4) reinforces it structurally. A fact and a forecast
must never be phrased with the same certainty, and the assembler carries the
category as metadata on every evidence item so the generator cannot lose track of
which bucket a statement came from.

## 4. Evidence & citations — every engineering claim is traceable

The generator emits **structured, claim-level output**, not free prose. Each
engineering statement is a `GroundedClaim { text, category, citations[],
confidence }`, and **`citations` must be non-empty for any engineering claim.**
Citations reference:

- **Finding IDs** (deterministic + diagnosed + learned)
- **Rule IDs** (which rule fired, with its instance)
- **Artifact IDs** (the analytic EngineResult behind a number)
- **Forecast model/version** (e.g. `forecast:holt_winters_additive@0.1.0`)
- **Pattern model/version** (e.g. `isolation_forest@…`, `gmm@…`)

A **post-generation grounding validator** checks every claim: each cited id must
exist in the retrieved bundle, and each engineering claim must carry ≥1 citation.
**Claims that fail validation are dropped or the response is rejected** — the
model is not trusted to self-police; the framework enforces it. Narrative
connective tissue ("the following three findings are related") is allowed
uncited; **any statement asserting an engineering fact, diagnosis, or prediction
is not.** The citation tests (§ Implementation) fail the build if an uncited
engineering claim can reach output.

## 5. Confidence communication — never collapse into one number

The four confidence *kinds* stay distinct end-to-end and are surfaced with
distinct language:

| Source | Kind | How it is communicated |
|---|---|---|
| Deterministic analytics / DERIVED | **Certainty** | "is" / "measured at" — stated as fact |
| Rule Engine / DIAGNOSED | **Rule confidence** | "diagnosed (rule R-…, confidence 0.72)" |
| Pattern learning / LEARNED | **Pattern confidence** | "a learned hypothesis (confidence 0.6, model health …)" |
| Forecasting / LEARNED | **Forecast confidence** | "projected … (80% interval, backtest coverage 0.83)" |

There is **no single blended confidence score.** The response model carries each
claim's confidence *typed by source*, and the persona formatter (§9) may choose
plainer wording per audience but **may never merge kinds** — a plant manager
sees "likely / advisory" language, not a fabricated 0.71 that averages a fact and
a forecast. Collapsing kinds is treated as a defect, covered by a behaviour test.

## 6. Hallucination prevention — architectural, not hopeful

Safeguards, in layers:

1. **Retrieval-grounded only** — the model sees the bundle and nothing else; it
   has no tool to fetch more, no telemetry to reason over, no engine to call.
2. **Citation enforcement** (§4) — uncited engineering claims are mechanically
   removed; a response reduced to nothing but unsupported claims degrades to an
   explicit "insufficient evidence" answer.
3. **Recommendations are quoted, never generated** — maintenance actions and
   failure modes originate **only** from deterministic rules or a curated
   engineering-knowledge base, and are inserted by reference. The LLM **rephrases
   a curated recommendation; it never authors one.** No rule/knowledge entry ⇒ no
   recommendation.
4. **Authorised "I don't know"** — the §3 "Insufficient Evidence" section and the
   persona templates make refusal a **valid, expected** output, so the model is
   never cornered into inventing to satisfy a question.
5. **No new failure modes** — the vocabulary of diagnoses/failure modes is closed
   to what the Finding/Rule catalogs define; the model cannot introduce a
   mechanism the stack has not asserted.

The test suite includes **adversarial grounding tests**: questions whose honest
answer is "unknown," questions inviting a fabricated recommendation, and
questions about assets/periods with no evidence — each must yield an explicit
"insufficient evidence / not diagnosed" response, never a confident invention.

## 7. Conversation memory — presentation only, never mutation

Conversation history influences **wording, focus, and follow-up framing** — and
nothing else. It **cannot** modify findings, diagnoses, forecasts, or graph
contents; those stores are read-only to this layer. Concretely:

- History is used to resolve references ("what about the *other* compressor?"),
  set verbosity, and avoid repetition.
- Every turn **re-retrieves a fresh EvidenceBundle** from the current stores;
  memory never substitutes for retrieval and never caches a "fact" that could go
  stale or be contradicted by the live graph.
- No turn can write back to any engineering store. Memory is a UI convenience,
  architecturally isolated from the evidence layer.

## 8. Report generation — one grounded evidence set, many structured documents

All report types are **templated projections over the same `EvidenceBundle`**,
so a daily report and an RCA of the same asset/window cite the same ids and never
contradict each other:

- **Daily Asset Health Report** — status, active findings, open hypotheses,
  forecast watch-items.
- **Maintenance Summary** — diagnosed conditions + *curated* recommended actions
  (quoted, §6.3), prioritised by severity/reliability.
- **Forecast Summary** — approach hypotheses with lead time + intervals + backtest
  coverage, explicitly labelled advisory.
- **Root Cause Analysis** — a diagnosis walked back along `TRIGGERED_BY` /
  `PRECEDES` edges to its antecedent findings and artifacts.
- **Executive Summary** — high-level state + material risks, hypotheses clearly
  marked as such.
- **Engineering Investigation Report** — the full evidentiary chain with all
  citations, for an engineer to audit.

Every report is **regenerable and deterministic given a fixed bundle** (modulo
LLM sampling, which is constrained by the grounded schema); the *evidence* is
reproducible even if the prose varies.

## 9. Multi-persona — same evidence, different presentation

Personas change **only** presentation (vocabulary, depth, what to foreground);
the underlying cited evidence is **identical** across all of them:

| Persona | Foregrounds | Register |
|---|---|---|
| Plant Operator | immediate state, what to watch now | plain, actionable |
| Maintenance Engineer | diagnosed conditions + recommended actions | procedural |
| Reliability Engineer | trends, hypotheses, evidence chains, model health | analytical, full citations |
| Plant Manager | asset-level risk, priorities, lead times | summarised, risk-framed |
| Executive | fleet posture, material risks | brief, outcome-oriented |

A **persona-invariance test** asserts that for a fixed bundle, the *set of cited
ids* is the same across personas — proving personas re-present rather than
re-decide. Only the wording and selection/ordering differ; no persona may
introduce a claim another persona's evidence didn't support.

## 10. Explainability — answerable without recomputation

For any conclusion, the layer can answer, purely from the retrieved bundle and
the graph edges — **recomputing nothing**:

- **Why was this reached?** — the finding/diagnosis and its summary/detail.
- **Which evidence supports it?** — the cited Finding/Artifact ids + their
  evidence values.
- **Which rules fired?** — the Rule ids and their antecedents (persisted
  reasoning, ADR-015).
- **Which findings contributed?** — the `TRIGGERED_BY` / antecedent chain.
- **Which hypotheses remain uncertain?** — LEARNED findings with their confidence
  + model health, explicitly flagged as unconfirmed.

Explainability is a **graph/citation walk, not a re-analysis.** The LLM narrates
the existing evidence chain; it never re-opens the computation.

## 11. Interaction WITHOUT changing deterministic conclusions

- Remove the LLM layer and **every** deterministic output, finding, diagnosis,
  forecast, and parity test is **byte-identical.** It is strictly additive.
- The layer holds **no write access** to any engineering store; it cannot upsert
  a node, fire a rule, or emit a Finding.
- It reads threshold/finding/rule *definitions and outputs*; it calls **no**
  engine and touches **no** telemetry for reasoning.

## 12. Example — SC-126 (honest expectation)

Asked "is SC-126 healthy?", the layer retrieves: DERIVED stability facts, the
`THRESHOLD_CONFIG_REVIEW_RECOMMENDED` diagnosis (mis-set bands, not a fault), the
quiet novelty/regime hypotheses, and the four advisory forecast approaches that
land on the *same* mis-set sensors. The Reliability-Engineer answer:

> *"SC-126 is operating as a stable baseload machine (fact: statistics + reliability, artifacts …). No fault is diagnosed. One diagnosis stands: several thresholds appear mis-configured relative to normal operation (rule R-THR-CONFIG, confidence …), not an equipment problem. Forecasts project discharge pressure / oil pressure to approach those same (mis-set) limits within ~Nh — advisory hypotheses (80% interval, backtest coverage …), not predicted breaches. No maintenance action is warranted beyond reviewing the threshold configuration."*

Every clause carries an id; the honest "no fault, just mis-set limits" survives
intact — the LLM does **not** upgrade advisory forecasts into an alarm.

## 13. Deferred (not in this layer)

Autonomous decision-making, automatic rule creation, automatic maintenance
execution, direct telemetry reasoning, any path that bypasses analytics or the
Rule Engine, Phase C supervised learning, and dashboard/API/deployment wiring
(consume this layer's outputs but are separate work).

## 14. Decision & implementation scope (after approval)

Adopt the LLM as a **grounded, citation-enforced communication layer** with the
responsibility boundary of §1, curated evidence retrieval of §2 (no telemetry
reasoning), five-category prompt assembly of §3, mandatory claim-level citations
of §4, four distinct confidence kinds of §5, architectural hallucination
safeguards of §6, presentation-only memory of §7, template-projected reports of
§8, presentation-only personas of §9, and recompute-free explainability of §10.

On approval, implement **only**:

- **LLM orchestration layer** (`senseminds/llm/`) — the turn/report pipeline.
- **Retrieval pipeline** — `EvidenceBundle` assembly from graph/findings/rules/
  forecasts/patterns (read-only), asset/window-scoped.
- **Prompt builder** — five-category grounded prompt assembly.
- **Grounding & citation framework** — `GroundedClaim` schema + post-generation
  validator that drops/rejects uncited engineering claims.
- **Report generation** — the six report templates over one bundle.
- **Multi-persona formatting** — five personas, evidence-invariant.
- **Hallucination safeguards** — insufficient-evidence handling, quoted-only
  recommendations, closed failure-mode vocabulary.
- **Behaviour tests, grounding tests, citation tests** — including adversarial
  "unknown," persona-invariance, memory-cannot-mutate, and boundary-isolation
  (remove-the-LLM parity) tests.

**Provider abstraction:** a pluggable `LanguageModel` interface (like
`ForecastModel`) so a deterministic stub model backs all grounding/citation tests
offline, and a real provider plugs in without architectural change. Grounding is
provider-independent and fully testable without network access.

**Do NOT implement:** autonomous decisions, automatic rule creation, automatic
maintenance execution, direct telemetry reasoning, or any component bypassing the
deterministic analytics / Rule Engine.

**Stop condition:** stop after the LLM layer passes **all** grounding,
explainability, citation, and hallucination-prevention tests. At that point the
architecture is complete:

> Industrial Data → Engineering Analytics → Engineering Knowledge →
> Deterministic Reasoning → Learned Intelligence → Forecasting →
> **Grounded LLM Communication**

**Awaiting approval.** On the go-ahead, the first implementation unit would be the
read-only `EvidenceBundle` retrieval + `GroundedClaim` schema + citation
validator with a deterministic stub `LanguageModel` and the citation/grounding
test spine — proving the safety frame before any prose generation is wired.
