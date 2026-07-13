import { useState } from "react";
import { useFleet } from "../lib/useFleet";
import type { Severity } from "../lib/api";
import { SEVERITY } from "../lib/ui";
import { Empty, FindingCard, Icon, Spinner } from "../components/ui";

export default function Findings() {
  const { assets, error } = useFleet();
  const [unit, setUnit] = useState("all");
  const [sev, setSev] = useState<"all" | Severity>("all");

  if (error) return <Empty icon="cloud_off" title="Cannot reach the platform" hint={error} />;
  if (!assets) return <Spinner label="Loading findings…" />;

  const all = assets.flatMap((a) => a.findings);
  const shown = all
    .filter((f) => unit === "all" || f.equipment_key === unit)
    .filter((f) => sev === "all" || f.severity === sev)
    .sort((a, b) => {
      const rank: Severity[] = ["critical", "warning", "info", "ok"];
      return rank.indexOf(a.severity) - rank.indexOf(b.severity);
    });

  return (
    <>
      <header className="animate-rise">
        <span className="eyebrow">Evidence</span>
        <h1 className="mt-1 text-2xl lg:text-3xl font-extrabold tracking-tight">
          Findings &amp; Diagnoses
        </h1>
        <p className="mt-1 text-sm text-ink-muted max-w-2xl">
          Every finding is deterministic or rule-derived, carries its own evidence, and is
          cited by id whenever the Copilot mentions it.
        </p>
      </header>

      {/* Filters — one row above the content */}
      <div className="flex flex-wrap items-center gap-2">
        <select value={unit} onChange={(e) => setUnit(e.target.value)}
          className="rounded-xl border border-line bg-card px-3 py-2 text-sm font-medium
                     outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-50">
          <option value="all">All assets</option>
          {assets.map((a) => <option key={a.unit} value={a.unit}>{a.unit}</option>)}
        </select>

        <div className="flex flex-wrap gap-1.5">
          {(["all", "critical", "warning", "info", "ok"] as const).map((s) => (
            <button key={s} onClick={() => setSev(s)}
              className={`pill ring-1 ${
                sev === s
                  ? "bg-brand-600 text-white ring-brand-600"
                  : "bg-card text-ink-soft ring-line hover:bg-canvas"
              }`}>
              {s !== "all" && (
                <Icon name={SEVERITY[s].icon} className="text-[13px]" />
              )}
              {s === "all" ? "All" : SEVERITY[s].label}
              <span className="num opacity-70">
                {s === "all" ? all.length : all.filter((f) => f.severity === s).length}
              </span>
            </button>
          ))}
        </div>
      </div>

      {shown.length ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {shown.map((f) => <FindingCard key={f.finding_id} f={f} />)}
        </div>
      ) : (
        <Empty icon="task_alt" title="No findings match these filters" />
      )}
    </>
  );
}
