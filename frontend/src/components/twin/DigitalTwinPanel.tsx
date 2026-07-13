/** Digital Twin tab.
 *
 *  Three separate blocks, deliberately not merged:
 *    1. the machine        — rotatable, sensors lit by their state
 *    2. overall state      — one honest verdict for the whole machine
 *    3. sensor readings    — the individual numbers, plainly listed
 *
 *  three.js is loaded only when this tab is opened, so the rest of the dashboard
 *  stays light.
 */
import { Suspense, lazy, useMemo, useState } from "react";
import type { Asset, Finding, Severity, Telemetry } from "../../lib/api";
import { SEVERITY, healthScore, prettySensor, worst } from "../../lib/ui";
import { HealthRing, Icon, Spinner } from "../ui";
import type { Hot } from "./Twin";

const Twin = lazy(() => import("./Twin"));

/** A sensor is "out of range" when its latest reading leaves its supplied band. */
function breaching(t: Telemetry["sensors"][number]): boolean {
  if (!t.threshold || !t.latest) return false;
  const { low, high } = t.threshold;
  return (low != null && t.latest.value < low) || (high != null && t.latest.value > high);
}

export default function DigitalTwinPanel({
  asset, findings, telemetry,
}: {
  asset: Asset;
  findings: Finding[];
  telemetry: Telemetry | null;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const hots = useMemo(() => {
    const out: Record<string, Hot> = {};
    for (const s of asset.sensors) {
      const trace = telemetry?.sensors.find((t) => t.key === s.key);
      const fromFindings = worst(
        findings.filter((f) => f.target_key === s.key).map((f) => f.severity),
      );
      const sev: Severity =
        trace && breaching(trace) ? "critical" : fromFindings;
      out[s.key] = { key: s.key, severity: sev, trace };
    }
    return out;
  }, [asset, findings, telemetry]);

  const list = Object.values(hots);
  const overall = worst(list.map((h) => h.severity));
  const S = SEVERITY[overall];
  const health = healthScore(findings.map((f) => f.severity));
  const counts = {
    critical: list.filter((h) => h.severity === "critical").length,
    warning: list.filter((h) => h.severity === "warning").length,
  };
  const sel = selected ? hots[selected] : null;

  return (
    <section className="space-y-4 animate-rise">
      {/* ── 1. the machine ─────────────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 pt-4">
          <div>
            <p className="eyebrow">The machine</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              Drag to rotate · scroll to zoom · click a dot to see its reading
            </p>
          </div>
          <div className="flex items-center gap-3 text-[11px] font-semibold">
            {(["ok", "warning", "critical"] as Severity[]).map((s) => (
              <span key={s} className="inline-flex items-center gap-1 text-ink-muted">
                <span className={`h-2 w-2 rounded-full ${SEVERITY[s].dot}`} />
                {SEVERITY[s].label}
              </span>
            ))}
          </div>
        </div>

        <div className="h-[380px] sm:h-[440px]">
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center">
                <Spinner />
              </div>
            }
          >
            <Twin asset={asset} hots={hots} selected={selected}
                  onSelect={(k) => setSelected(k || null)} />
          </Suspense>
        </div>

        <p className="border-t border-line px-5 py-2 text-[11px] text-ink-3">
          A representative view of the equipment and its subsystems — not a
          scale model of the physical unit.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        {/* ── 2. overall state ─────────────────────────────────────── */}
        <div className="card p-5">
          <p className="eyebrow">Overall state</p>
          <div className="mt-3 flex items-center gap-4">
            <HealthRing score={health} />
            <div className="min-w-0">
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1
                                text-xs font-semibold ring-1 ${S.pill}`}>
                <Icon name={S.icon} className="text-[14px]" />
                {S.label}
              </span>
              <p className="mt-2 text-sm text-ink-soft leading-snug">
                {counts.critical > 0
                  ? `${counts.critical} sensor${counts.critical > 1 ? "s" : ""} past a safe limit.`
                  : counts.warning > 0
                    ? `${counts.warning} sensor${counts.warning > 1 ? "s" : ""} worth watching.`
                    : "All sensors within their normal range."}
              </p>
            </div>
          </div>
        </div>

        {/* ── 3. sensor readings ───────────────────────────────────── */}
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <p className="eyebrow">Sensor readings</p>
            {sel && (
              <button onClick={() => setSelected(null)}
                      className="text-xs font-semibold text-brand-600 hover:text-brand-700">
                Clear selection
              </button>
            )}
          </div>

          {!telemetry ? (
            <div className="flex justify-center py-6"><Spinner /></div>
          ) : (
            <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
              {list.map((h) => {
                const on = selected === h.key;
                const HS = SEVERITY[h.severity];
                return (
                  <li key={h.key}>
                    <button
                      onClick={() => setSelected(on ? null : h.key)}
                      className={`flex w-full items-center justify-between gap-3 rounded-xl border
                                  px-3 py-2 text-left transition ${
                        on
                          ? "border-brand-300 bg-brand-50"
                          : "border-line bg-canvas hover:border-brand-200"
                      }`}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${HS.dot}`} />
                        <span className="truncate text-sm font-medium">
                          {prettySensor(h.key)}
                        </span>
                      </span>
                      <span className="num shrink-0 text-sm font-semibold">
                        {h.trace?.latest ? h.trace.latest.value : "—"}
                        <span className="ml-0.5 text-[11px] font-normal text-ink-muted">
                          {h.trace?.unit_symbol}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {sel?.trace?.threshold && (
            <p className="mt-3 num text-[11px] text-ink-3">
              {prettySensor(sel.key)} · normal range{" "}
              {sel.trace.threshold.low ?? "any"} – {sel.trace.threshold.high ?? "any"}{" "}
              {sel.trace.unit_symbol}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
