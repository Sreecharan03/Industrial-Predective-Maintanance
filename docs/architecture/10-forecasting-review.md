# ADR-017 — Forecasting: Architecture Review (Phase B, Increment 2)

Status: **ACCEPTED (2026-07-10)** with one refinement — see §13 (pluggable
models + backtest-driven selection). Builds on ADR-016 (Pattern Learning;
forecasting was staged here) and ADR-007 (three-phase ML).

## 0. Context and the one honest differentiator

Forecasting is legitimately Phase B (label-free) for a reason worth stating up
front: **its target is observed.** A sensor's future value *is* eventually
recorded, so a forecast can be **backtested and scored** (MAE, interval
coverage) — unlike failure prediction, whose target (a failure) is never
labelled here. Forecasting therefore earns a place now *because it can be
validated*, while failure prediction stays deferred to Phase C.

The value proposition: **lead time**. "Oil temperature is trending toward its
limit; projected to reach it in ~3 days ±1 at the 80% interval" — a
forward-looking hypothesis for engineer attention, never an alarm.

## 1. Role — predictive trend estimation, NOT failure prediction

| Forecasting IS | Forecasting IS NOT |
|---|---|
| Short-horizon estimation of a sensor's own future trend, with uncertainty | Failure / breakdown prediction |
| A **LEARNED hypothesis** (advisory), backtest-validated | A deterministic verdict or fact |
| "value likely in range [a, b] in N hours" | "the machine will fail" / RUL |
| Owned by Pattern Learning (future) | Not owned by the Threshold engine (present) |

It forecasts *values*; it never decides breaches (that is the Threshold engine's
job for the present). A forecast crossing a threshold is a **future hypothesis**,
kept strictly separate from the deterministic present-state verdict.

## 2. Data reality & preprocessing (this data is hard)

30-min *irregular* cadence with multi-week gaps. Preprocessing (deterministic,
in the feature pipeline family):
- **Resample to a regular grid** (e.g. 30-min or hourly) per sensor.
- **Never forecast across or into a large gap** — a forecast origin must sit at
  the end of a contiguous, sufficiently-covered window; horizons that would
  extend into a known gap are suppressed.
- **Condition on operating state** — forecast within the machine's current
  regime (a full-load trend is not a shutdown trend); use the Operating-State
  result to avoid mixing regimes.
- **Down-weight/skip untrustworthy sensors** — a forecast on a drifting sensor
  is flagged via ModelHealth (ADR-016 R1).

## 3. Model selection — statistical baselines first (staged)

**Ship first: robust statistical baselines.**
- **Seasonal-naive** (last-day / last-week value) — the honest baseline every
  other model must beat.
- **Exponential smoothing / Holt-Winters (ETS)** — trend + daily/weekly
  seasonality, cheap, explainable, native prediction intervals.
- Optionally **Theta / STL-decomposition** for trend+seasonal separation.

**Defer sequence/deep models** (ARIMA-family beyond ETS, Prophet, NeuralProphet,
LSTM/TCN) until a **measured backtest gap** justifies them. On irregular, gappy,
unlabelled 30-min data, deep sequence models overfit, are hard to explain, and
rarely beat a well-tuned ETS at short horizons. **Complexity must be earned by
a backtest, not assumed.**

## 4. Forecast horizon & uncertainty

- **Short horizon only** — hours to a few days (e.g. ≤ 72 h), capped by cadence,
  coverage, and gap structure. Horizon never exceeds what the data supports.
- **Always prediction intervals, never a bare point forecast** — every forecast
  carries e.g. 50%/80% intervals. Uncertainty **grows with horizon**; beyond a
  confidence floor (interval too wide to be useful) the forecast is **suppressed**
  rather than shown.
- **Backtest-derived calibration** — interval widths are validated by walk-
  forward backtest coverage (does the 80% interval actually contain ~80% of
  actuals?).

## 5. Forecasts as LEARNED hypotheses in the Knowledge Graph

A `ForecastResult` yields, all `origin=LEARNED`, `status=hypothesis`:
- **`FORECAST_THRESHOLD_APPROACH`** LEARNED finding — emitted only when a
  forecast **interval** crosses a threshold *definition* within the horizon,
  carrying `lead_time`, the crossing probability, the interval, and the model
  version. Framed as "projected to approach limit," never "will breach."
- A **`DiscoveredPattern`/ForecastSeries** node (`kind="forecast"`) with horizon,
  method, interval calibration, and lifecycle; edges `DISCOVERED_BY` (→ model),
  `SUGGESTS` (finding → forecast). Reuses the ADR-016 `PatternProjector`.
- The forecast **series values are not stored in the graph** (that is telemetry,
  ADR-014) — only the hypothesis + a reference to the forecast artifact.

## 6. Interaction WITHOUT changing deterministic conclusions

- **Thresholds:** forecasting **reads threshold definitions** (bounds from the
  catalog/graph) to compute a future crossing; it **never calls the Threshold
  engine and never alters its present-state verdict**. Present breach = Threshold
  engine (fact); future approach = forecast (hypothesis). No overlap, no
  mutation.
- **Rules:** a forecast hypothesis is **optional, capped-weight corroboration**
  only (e.g. an `ESCALATION` rule may raise attention when a deterministic
  WARNING coincides with a `FORECAST_THRESHOLD_APPROACH`) — never a *required*
  antecedent, never changing a diagnosis's validity (ADR-015 §1/§6).
- **Pattern Learning:** forecasting is a sibling model kind; forecast *error*
  can later feed novelty, but output stays `LEARNED`. DERIVED features feed
  models; DIAGNOSED/LEARNED never do (ADR-013, no circularity).
- **Deterministic independence:** remove forecasting and every deterministic
  output and parity test is byte-identical. Strictly additive/advisory.

## 7. Explainability

Every forecast hypothesis exposes (via evidence): the **method** (e.g.
Holt-Winters), the **trend + seasonal components** it used, the **origin window**
and operating state it was conditioned on, the **interval**, and the
**lead-time-to-threshold with its uncertainty**. The LLM/Dashboard say *"discharge
temp is trending up on its daily cycle; at the current rate it reaches the 76 °C
limit in ~3 days (80% interval 2–5 days)"* — not "forecast = 74.1."

## 8. Model versioning & reproducibility (+ backtesting)

As ADR-016: seeds (where stochastic), a **ModelRegistry** entry per forecast
model (`model_id, version, trained_at, training_window, feature_schema, seed,
hyperparameters`), and a snapshotted input hash ⇒ reproducible. **New here:
walk-forward backtesting** — because the target is observed, each model is scored
on held-out actuals (MAE/MAPE + interval coverage). These scores populate
`ModelHealth` and gate whether a forecast is trustworthy enough to surface.

## 9. Edge cases

Insufficient/short history → no forecast. Large gaps → no forecast across/into
them; horizon truncated. Non-stationary / regime change → condition on operating
state; flag if the origin regime is unstable. Flat/constant sensors → trivial
forecast, wide-relative-uncertainty suppressed. Untrustworthy sensor →
down-weighted/skipped, flagged in ModelHealth. Strong seasonality → ETS/STL
captures daily/weekly; seasonal-naive as fallback. Horizon beyond data support →
capped. Poor backtest score → forecast withheld (not surfaced as a hypothesis).

## 10. Deferred (not in this increment)

Sequence/deep models (until a backtest earns them), multivariate/cross-sensor
forecasting, probabilistic deep models, RUL/failure prediction (Phase C), and
the LLM.

## 11. Example — SC-126 (honest expectation)

SC-126 is a stable baseload machine, so short-horizon forecasts will be
**near-flat with tight, well-calibrated intervals**, and **no
`FORECAST_THRESHOLD_APPROACH`** will fire (nothing is trending toward a real
limit) — the correct, quiet outcome that *confirms* stability. The value appears
on sensors/periods that genuinely trend (e.g. a slow oil-temperature rise on a
degrading unit), where a lead-time hypothesis is surfaced for triage — advisory,
uncertainty-bounded, and subordinate to the deterministic diagnosis.

## 12. Decision & next step

Adopt: forecasting as a label-free, **backtest-validated** predictive-trend
layer producing `LEARNED` hypotheses (§1); resample + gap-aware + state-
conditioned preprocessing (§2); **statistical baselines first, deep models only
when a backtest earns them** (§3); **intervals always, horizon capped, low-
confidence suppressed** (§4); forecasts as KG hypotheses reading threshold
*definitions* without touching the Threshold engine (§5–6); explainable
components (§7); registry + reproducibility + walk-forward backtesting (§8).

**Awaiting approval.** On the go-ahead, the first implementation unit would be
the resample/gap-aware forecasting feature prep + a `ForecastModel` interface +
seasonal-naive and Holt-Winters baselines with walk-forward backtesting and
prediction intervals, emitting `LEARNED` forecast hypotheses through the
existing `PatternProjector` — with reproducibility, backtest, and boundary-
isolation tests. No deep models, no LLM.

## 13. Accepted refinement — pluggable models, backtest-driven selection

ETS is **not** hard-coded as the permanent model, and no deep model is a default.
Forecasting is a **pluggable model architecture**:

- A stable **`ForecastModel` interface** (`fit` / `forecast(horizon) → mean +
  intervals`) that Seasonal-Naive and Holt-Winters/ETS implement now, and that
  NeuralProphet / Prophet / LSTM / TCN / Transformer can implement **later
  without changing any surrounding architecture**.
- A **`ModelSelector`** chooses the production model **per sensor** purely by
  objective **walk-forward backtesting** on our own data: `MAE`, `RMSE`, `MAPE`,
  **prediction-interval coverage**, plus **computational cost** and
  **explainability** as tie-breakers.
- **Guiding principle (enforced in code):** *no model earns a production slot
  unless it beats the simpler baseline by a margin on our industrial data.* The
  selector defaults to the Seasonal-Naive/ETS baseline and only promotes a more
  complex model when the backtest demonstrably justifies it — and always as an
  **additional** implementation, never a wholesale replacement.

This turns "which model?" from an architectural decision into a **measured,
data-driven, reproducible** one, and keeps the door open to deep models without
committing to them prematurely.
