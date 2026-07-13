import { Link } from "react-router-dom";
import { useFleet } from "../lib/useFleet";
import { CLASSES, SEVERITY, healthScore } from "../lib/ui";
import {
  Empty, FindingCard, HealthRing, Icon, Section, Spinner, StatCard, StatusPill,
} from "../components/ui";

export default function Overview() {
  const { assets, error } = useFleet();

  if (error) return <Empty icon="cloud_off" title="Cannot reach the platform" hint={error} />;
  if (!assets) return <Spinner label="Loading fleet…" />;
  if (!assets.length)
    return (
      <Empty
        icon="precision_manufacturing"
        title="No assets analysed yet"
        hint="Run an analysis from an asset page, or start the worker to process the fleet."
      />
    );

  const all = assets.flatMap((a) => a.findings);
  const plantHealth = healthScore(all.map((f) => f.severity));
  const critical = all.filter((f) => f.severity === "critical").length;
  const watch = all.filter((f) => f.severity === "warning").length;
  const diagnoses = all.filter((f) => f.origin === "diagnosed").length;
  const sensors = assets.reduce((s, a) => s + a.sensor_count, 0);
  const recent = [...all]
    .sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "critical" ? -1 : 1))
    .slice(0, 4);

  return (
    <>
      {/* Hero */}
      <section className="card p-6 lg:p-7 animate-rise overflow-hidden relative">
        <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-brand-50 blur-2xl" />
        <div className="relative flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <HealthRing score={plantHealth} size={104} />
          <div className="flex-1 min-w-0">
            <p className="eyebrow">Central Dashboard</p>
            <h1 className="mt-1 text-2xl lg:text-3xl font-extrabold tracking-tight">
              Plant health is{" "}
              <span className={plantHealth >= 85 ? "text-ok" : plantHealth >= 60 ? "text-warn" : "text-crit"}>
                {plantHealth >= 85 ? "steady" : plantHealth >= 60 ? "worth a look" : "needs attention"}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-ink-soft max-w-2xl leading-relaxed">
              {all.length} findings across {assets.length} assets — all deterministic or
              rule-derived, none invented. Threshold findings mean a{" "}
              <b className="text-ink">limit is mis-set</b>, not that a machine is failing.
            </p>
          </div>
        </div>
      </section>

      {/* KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Assets monitored" value={assets.length} icon="precision_manufacturing" />
        <StatCard label="Sensors" value={sensors} icon="sensors" tone="info" />
        <StatCard
          label="Needs attention" value={critical + watch} icon="warning"
          tone={critical ? "crit" : watch ? "warn" : "ok"}
          foot={<span>{critical} critical · {watch} watch</span>}
        />
        <StatCard label="Diagnoses" value={diagnoses} icon="clinical_notes" tone="brand"
          foot="Rule-derived, with confidence" />
      </div>

      {/* Fleet */}
      <Section title="Fleet" subtitle="Health rolls up from each asset's findings">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {assets.map((a) => {
            const meta = CLASSES[a.equipment_class];
            return (
              <Link key={a.unit} to={`/asset/${encodeURIComponent(a.unit)}`}
                className="card card-hover p-5 group animate-rise">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-ink-muted">
                      <Icon name={meta?.icon ?? "memory"} className="text-[18px]" />
                      <span className="text-xs font-semibold">{meta?.label ?? a.equipment_class}</span>
                    </div>
                    <p className="mt-1.5 font-bold text-lg tracking-tight truncate">{a.unit}</p>
                  </div>
                  <HealthRing score={a.health} size={64} />
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <StatusPill severity={a.severity} />
                  <span className="text-xs text-ink-muted num">
                    {a.findings.length} findings
                  </span>
                </div>

                {/* severity mix — a tiny stacked bar, 2px surface gaps between segments */}
                <div className="mt-4 flex gap-[2px] h-1.5">
                  {(["critical", "warning", "info", "ok"] as const).map((s) => {
                    const n = a.findings.filter((f) => f.severity === s).length;
                    if (!n) return null;
                    return (
                      <span key={s} title={`${n} ${SEVERITY[s].label}`}
                        className={`${SEVERITY[s].dot} rounded-full`}
                        style={{ flex: n }} />
                    );
                  })}
                  {!a.findings.length && <span className="flex-1 rounded-full bg-line" />}
                </div>

                <p className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-600
                              opacity-0 group-hover:opacity-100 transition-opacity">
                  Inspect <Icon name="arrow_forward" className="text-[16px]" />
                </p>
              </Link>
            );
          })}
        </div>
      </Section>

      {/* Recent findings */}
      <Section
        title="Needs a look"
        subtitle="Highest-severity findings across the plant"
        action={
          <Link to="/findings" className="btn-quiet">
            All findings <Icon name="arrow_forward" className="text-[16px]" />
          </Link>
        }
      >
        {recent.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {recent.map((f) => <FindingCard key={f.finding_id} f={f} />)}
          </div>
        ) : (
          <Empty icon="task_alt" title="Nothing needs attention" />
        )}
      </Section>
    </>
  );
}
