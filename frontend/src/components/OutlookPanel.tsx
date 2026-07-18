import { useEffect, useState } from "react";
import { api, type Outlook } from "../lib/api";
import { Empty, Icon, Spinner } from "./ui";

/** Forward-looking summary for one machine.
 *
 *  Deliberately NOT a "failure probability / remaining useful life" card: both
 *  need labelled breakdown history the plant does not have yet, so any number
 *  shown under those headings would be invented. Everything here traces to a
 *  recorded finding — the condition score is measured, the countdown comes from
 *  the backtest-selected forecaster, and the confidence is that model's own
 *  measured interval coverage. */

function Metric({
  label, value, unit, tone = "ink", hint,
}: {
  label: string; value: string; unit?: string;
  tone?: "ink" | "warn" | "crit" | "ok"; hint?: string;
}) {
  const colour = {
    ink: "text-ink", warn: "text-warn", crit: "text-crit", ok: "text-ok",
  }[tone];
  return (
    <div className="min-w-0">
      <p className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-ink-muted">{label}</p>
      <p className={`mt-1 font-extrabold tracking-tight tabular-nums ${colour}`}>
        <span className="text-[34px] leading-none">{value}</span>
        {unit && <span className="ml-1.5 text-[15px] font-bold">{unit}</span>}
      </p>
      {hint && <p className="mt-1 text-[11px] text-ink-muted leading-snug">{hint}</p>}
    </div>
  );
}

function Chip({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-canvas px-3.5 py-2.5 min-w-0">
      <p className="text-[10px] font-bold tracking-[0.09em] uppercase text-ink-muted">{label}</p>
      <p className="mt-0.5 font-mono text-[12.5px] font-semibold text-ink truncate">{value}</p>
      {sub && <p className="text-[10.5px] text-ink-muted truncate">{sub}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 *  PHASE C PREVIEW — MOCK DATA
 *
 *  This card shows the INTENDED design for supervised failure prediction
 *  and remaining useful life. The numbers are illustrative placeholders,
 *  not predictions: training either model needs a labelled breakdown
 *  history the plant has not provided yet (ADR-007 Phase C).
 *
 *  It lives in the presentation layer ON PURPOSE. Nothing here touches the
 *  API, the database, or a finding — so the Copilot, alert escalation and
 *  reports (which all read persisted evidence) can never pick these values
 *  up and repeat them as fact. The mock can be looked at; it cannot be used.
 * ------------------------------------------------------------------ */

/** Stable per-machine placeholders — the same machine always shows the same
 *  illustrative numbers, so the preview does not flicker between renders. */
function mockFor(unit: string) {
  let h = 0;
  for (let i = 0; i < unit.length; i++) h = (h * 31 + unit.charCodeAt(i)) >>> 0;
  const probability = 18 + (h % 380) / 10;         // 18.0 – 56.0 %
  const rulDays = 6 + (h % 47);                    // 6 – 52 days
  const confidence = 0.72 + ((h >> 3) % 24) / 100; // 0.72 – 0.95
  return {
    probability: probability.toFixed(1),
    rulDays,
    confidence: confidence.toFixed(2),
    confidenceLabel: confidence >= 0.85 ? "HIGH" : confidence >= 0.75 ? "MEDIUM" : "LOW",
  };
}

function MockFailurePrediction({ unit, drivers }: { unit: string; drivers: string[] }) {
  const m = mockFor(unit);
  const named = drivers.length
    ? drivers.map((d) => d.replace(/_/g, " ")).join(", ")
    : "vibration, bearing temperature, oil temperature";

  return (
    <section
      className="rounded-2xl border-2 border-dashed border-warn-ring bg-warn-soft/30
                 overflow-hidden animate-rise"
    >
      {/* Unmissable banner — this is the first thing read, by design. */}
      <div className="bg-warn text-white px-5 py-2.5 flex items-start gap-2">
        <Icon name="science" className="text-[18px] mt-px shrink-0" />
        <p className="text-[12px] font-bold leading-snug">
          MOCK DATA — DESIGN PREVIEW ONLY.
          <span className="font-semibold opacity-95">
            {" "}These numbers are illustrative placeholders, not predictions. Real values
            arrive once labelled breakdown history is available.
          </span>
        </p>
      </div>

      <div className="px-6 pt-5 pb-4 opacity-[0.72]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Icon name="auto_awesome" className="text-[22px] text-ink-muted" />
            <h3 className="text-[17px] font-extrabold tracking-tight text-ink-soft">
              Failure Prediction
            </h3>
          </div>
          <span className="pill bg-canvas text-ink-muted ring-1 ring-line text-[10px] font-bold">
            PHASE C · NOT TRAINED
          </span>
        </div>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Metric label="Failure probability" value={m.probability} unit="%" tone="ink"
            hint="Placeholder — needs labelled failures to compute." />
          <div className="sm:text-right">
            <Metric label="Remaining useful life" value={String(m.rulDays)} unit="days" tone="ink"
              hint="Placeholder — needs run-to-failure cycles to compute." />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Chip label="ML engine" value="XGBoost Multi-Feature"
            sub="illustrative — no such model is trained" />
          <Chip label="Confidence" value={`${m.confidenceLabel} (${m.confidence})`}
            sub="illustrative — unmeasurable without labels" />
        </div>

        <div className="mt-4">
          <p className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-ink-muted">
            Recommendation (example wording)
          </p>
          <div className="mt-1.5 rounded-xl bg-card border-l-4 border-line px-4 py-3">
            <p className="text-[13px] text-ink-soft leading-relaxed">
              Model flags abnormal readings: {named}. Review these parameters and schedule
              an inspection.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-warn-ring bg-warn-soft/60 px-6 py-3.5">
        <p className="text-[11.5px] text-ink-soft leading-relaxed">
          <b>What unlocks the real version:</b> a labelled failure history — breakdown dates,
          machine, cause and action taken. With roughly 30–50 labelled events per failure mode
          these fields become trained, validated predictions in this exact layout. The card
          above it (<b>Predictive Outlook</b>) is live and real today.
        </p>
      </div>
    </section>
  );
}

export default function OutlookPanel({ unit }: { unit: string }) {
  const [data, setData] = useState<Outlook | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const pull = () =>
      api.outlook(unit)
        .then((o) => { if (alive) { setData(o); setError(null); } })
        .catch((e) => { if (alive) setError(String(e.message ?? e)); });
    pull();
    const id = setInterval(pull, 30_000);   // follow the live loop
    return () => { alive = false; clearInterval(id); };
  }, [unit]);

  if (error) return <Empty icon="cloud_off" title="Cannot load the outlook" hint={error} />;
  if (!data) return <Spinner label="Building outlook…" />;

  const { soonest, novelty } = data;
  const condition = data.condition_score;
  const conditionTone = condition == null ? "ink"
    : condition >= 90 ? "ok" : condition >= 75 ? "warn" : "crit";
  const leadTone = data.critical_count > 0 ? "crit"
    : soonest && soonest.hours_ahead <= 2 ? "warn" : "ok";

  return (
    <div className="space-y-4">
      {/* ---- the headline card ---- */}
      <section className="card p-0 overflow-hidden animate-rise">
        <div className="flex items-center justify-between px-6 pt-5 pb-4">
          <div className="flex items-center gap-2.5">
            <Icon name="insights" className="text-[22px] text-brand-600" />
            <h3 className="text-[17px] font-extrabold tracking-tight text-brand-700">
              Predictive Outlook
            </h3>
          </div>
          <Icon name="neurology" className="text-[26px] text-ink-muted/40" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 px-6 pb-5">
          <Metric
            label="Condition score"
            value={condition == null ? "—" : condition.toFixed(1)}
            unit={condition == null ? undefined : "%"}
            tone={conditionTone}
            hint="Measured now, from readings — not a model estimate."
          />
          <div className="sm:text-right">
            <Metric
              label={data.critical_count > 0 ? "Limits breached" : "Time to limit"}
              value={
                data.critical_count > 0 ? String(data.critical_count)
                  : soonest ? `~${soonest.hours_ahead}` : "None"
              }
              unit={
                data.critical_count > 0 ? "now"
                  : soonest ? (soonest.hours_ahead === 1 ? "hour" : "hours") : undefined
              }
              tone={leadTone}
              hint={
                soonest ? `${soonest.sensor.replace(/_/g, " ")} → limit ${soonest.bound ?? "—"}`
                  : "No sensor projected to reach a limit."
              }
            />
          </div>
        </div>

        <div className="border-t border-line px-6 py-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Chip
            label="Forecast model"
            value={soonest ? soonest.model_name : "none active"}
            sub={soonest
              ? `v${soonest.model_version} · won walk-forward backtest`
              : "no limit approach projected"}
          />
          <Chip
            label="Confidence"
            value={soonest ? `${(soonest.interval_confidence * 100).toFixed(0)}% interval` : "—"}
            sub={soonest && soonest.backtest_mae != null
              ? `measured backtest MAE ${soonest.backtest_mae.toFixed(4)}`
              : "measured on held-out folds"}
          />
        </div>

        {/* ---- what it means + the honest caveat ---- */}
        <div className="px-6 pb-5 space-y-3">
          <div>
            <p className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-ink-muted">
              What this means
            </p>
            <p className="mt-1.5 text-[14px] font-semibold text-ink leading-snug">
              {data.headline}
            </p>
          </div>

          <div className="rounded-xl bg-canvas border-l-4 border-brand-500 px-4 py-3">
            <p className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-ink-muted">
              Recommended next step
            </p>
            <p className="mt-1 text-[13px] text-ink-soft leading-relaxed">
              {data.recommendation}
            </p>
            {data.recommendation_citations.length > 0 && (
              <p className="mt-2 font-mono text-[10px] text-ink-muted">
                evidence: {data.recommendation_citations.map((c) => c.slice(0, 12)).join(" · ")}
              </p>
            )}
          </div>

          <p className="flex gap-2 text-[11.5px] text-ink-muted leading-snug">
            <Icon name="info" className="text-[14px] mt-px shrink-0" />
            <span>{data.caveat}</span>
          </p>
        </div>
      </section>

      {/* ---- behaviour vs history ---- */}
      {novelty && (
        <section className="card p-5 animate-rise">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-ink-muted">
                Behaviour vs. its own history
              </p>
              <p className="mt-1 text-[15px] font-bold">
                {novelty.windows} period{novelty.windows !== 1 ? "s" : ""} unlike this machine's norm
              </p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-[26px] font-extrabold tabular-nums text-ink">
                {novelty.score.toFixed(2)}
              </p>
              <p className="text-[10px] text-ink-muted font-mono">{novelty.model_name}</p>
            </div>
          </div>
          {novelty.top_features.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {novelty.top_features.map((f) => (
                <div key={f.feature} className="flex items-center gap-3">
                  <span className="text-[12px] text-ink-soft flex-1 truncate">
                    {f.feature.replace(/_/g, " ")}
                  </span>
                  <div className="w-28 h-1.5 rounded-full bg-canvas overflow-hidden">
                    <div className="h-full rounded-full bg-brand-500"
                      style={{ width: `${Math.min(Math.abs(f.deviation) * 33, 100)}%` }} />
                  </div>
                  <span className="text-[11px] font-mono tabular-nums text-ink-muted w-12 text-right">
                    {f.deviation > 0 ? "+" : ""}{f.deviation.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-[11.5px] text-ink-muted">
            An early signal that behaviour has shifted — not a fault, and not confirmed.
          </p>
        </section>
      )}

      {/* ---- Phase C design preview (mock, clearly marked) ---- */}
      <MockFailurePrediction
        unit={unit}
        drivers={(novelty?.top_features ?? []).map((f) => f.feature)}
      />

      {/* ---- every projected approach ---- */}
      {data.forecasts.length > 0 && (
        <section className="card p-5 animate-rise">
          <p className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-ink-muted">
            All projected limit approaches
          </p>
          <div className="mt-3 space-y-2">
            {data.forecasts.map((f) => (
              <div key={f.finding_id}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line
                           last:border-0 pb-2 last:pb-0">
                <span className="text-[13px] font-semibold flex-1 min-w-0 truncate">
                  {f.sensor.replace(/_/g, " ")}
                </span>
                <span className="text-[13px] font-bold tabular-nums">
                  ~{f.hours_ahead}h
                </span>
                <span className="text-[11px] text-ink-muted tabular-nums">
                  {f.projected_value ?? "—"} → limit {f.bound ?? "—"}
                </span>
                <span className="text-[10px] font-mono text-ink-muted">{f.model_name}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
