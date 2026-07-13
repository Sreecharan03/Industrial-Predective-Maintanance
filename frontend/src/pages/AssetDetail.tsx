import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api, type Asset, type EngineRun, type Finding, type Report, type Telemetry,
} from "../lib/api";
import { SensorChart, isBreaching } from "../components/SensorChart";
import { CLASSES, SEVERITY, healthScore, prettySensor, worst } from "../lib/ui";
import {
  Empty, FindingCard, HealthRing, Icon, Spinner, StatCard, StatusPill,
} from "../components/ui";

type Tab = "findings" | "sensors" | "graph" | "reports" | "runs";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "findings", label: "Findings", icon: "fact_check" },
  { id: "sensors", label: "Sensors", icon: "sensors" },
  { id: "graph", label: "Knowledge Graph", icon: "graph_3" },
  { id: "reports", label: "Reports", icon: "description" },
  { id: "runs", label: "Runs", icon: "history" },
];

export default function AssetDetail() {
  const { unit = "" } = useParams();
  const [asset, setAsset] = useState<Asset | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [runs, setRuns] = useState<EngineRun[]>([]);
  const [graph, setGraph] = useState<{ nodes: unknown[]; edges: unknown[] } | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [hours, setHours] = useState(6);
  const [tab, setTab] = useState<Tab>("findings");
  const [filter, setFilter] = useState<"all" | "derived" | "diagnosed" | "learned">("all");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const [a, f, r, g, ru] = await Promise.all([
      api.asset(unit).catch(() => null),
      api.findings(unit).catch(() => []),
      api.reports(unit).catch(() => []),
      api.graph(unit).catch(() => null),
      api.runs(unit).catch(() => []),
    ]);
    setAsset(a); setFindings(f); setReports(r); setGraph(g); setRuns(ru);
    setLoading(false);
  };

  useEffect(() => { setLoading(true); load(); /* eslint-disable-next-line */ }, [unit]);

  // Telemetry is fetched only when it is actually being looked at (ADR-018: raw
  // readings are an explicit request, never a default), and refreshed on the
  // simulator's 30s cadence so the chart tracks the live feed.
  useEffect(() => {
    if (tab !== "sensors" || !unit) return;
    let alive = true;
    const pull = () =>
      api.telemetry(unit, hours).then((t) => { if (alive) setTelemetry(t); }).catch(() => {});
    pull();
    const id = setInterval(pull, 30_000);
    return () => { alive = false; clearInterval(id); };
  }, [unit, tab, hours]);

  const analyse = async () => {
    setBusy(true); setNote("");
    try {
      const res = await api.analyze(unit);
      setNote(res.replayed
        ? "No new data — the existing analysis is already current."
        : `Analysis complete · ${res.finding_count} findings persisted.`);
      await load();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Spinner label={`Loading ${unit}…`} />;
  if (!asset)
    return (
      <Empty icon="search_off" title={`${unit} not analysed yet`}
        hint="Run an analysis to populate this asset." />
    );

  const meta = CLASSES[asset.equipment_class];
  const sevs = findings.map((f) => f.severity);
  const health = healthScore(sevs);
  const shown = findings.filter((f) => filter === "all" || f.origin === filter);

  return (
    <>
      {/* Header */}
      <header className="card p-6 animate-rise">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <HealthRing score={health} size={104} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-ink-muted">
              <Icon name={meta?.icon ?? "memory"} className="text-[18px]" />
              <span className="eyebrow">{meta?.label ?? asset.equipment_class}</span>
            </div>
            <h1 className="mt-1 text-3xl font-extrabold tracking-tight">{asset.unit}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusPill severity={worst(sevs)} />
              <span className="text-xs text-ink-muted num">{asset.sensors.length} sensors</span>
            </div>
          </div>
          <div className="flex flex-col items-stretch gap-2">
            <button className="btn-primary" onClick={analyse} disabled={busy}>
              <Icon name={busy ? "hourglass_top" : "play_arrow"} className="text-[18px]" />
              {busy ? "Analysing…" : "Run analysis"}
            </button>
            <Link to={`/copilot?unit=${encodeURIComponent(unit)}`} className="btn-quiet">
              <Icon name="auto_awesome" className="text-[16px]" /> Ask Copilot
            </Link>
          </div>
        </div>
        {note && (
          <p className="mt-4 flex items-center gap-2 rounded-xl bg-brand-50 ring-1 ring-brand-200
                        px-3 py-2 text-sm text-brand-700 font-medium">
            <Icon name="info" className="text-[16px]" /> {note}
          </p>
        )}
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Findings" value={findings.length} icon="fact_check" />
        <StatCard label="Diagnoses" value={findings.filter((f) => f.origin === "diagnosed").length}
          icon="clinical_notes" tone="brand" foot="Rule-derived" />
        <StatCard label="Watch / Critical"
          value={sevs.filter((s) => s === "warning" || s === "critical").length}
          icon="warning"
          tone={sevs.includes("critical") ? "crit" : sevs.includes("warning") ? "warn" : "ok"} />
        <StatCard label="Graph nodes" value={graph?.nodes.length ?? 0} icon="graph_3" tone="info"
          foot={`${graph?.edges.length ?? 0} relationships`} />
      </div>

      {/* Tabs */}
      <div className="border-b border-line flex gap-1 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold
                        border-b-2 -mb-px transition-colors whitespace-nowrap ${
              tab === t.id
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-ink-muted hover:text-ink"
            }`}>
            <Icon name={t.icon} className="text-[17px]" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "findings" && (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {(["all", "derived", "diagnosed", "learned"] as const).map((k) => (
              <button key={k} onClick={() => setFilter(k)}
                className={`pill ring-1 capitalize ${
                  filter === k
                    ? "bg-brand-600 text-white ring-brand-600"
                    : "bg-card text-ink-soft ring-line hover:bg-canvas"
                }`}>
                {k === "derived" ? "Facts" : k === "diagnosed" ? "Diagnoses"
                  : k === "learned" ? "Hypotheses" : "All"}
              </button>
            ))}
          </div>
          {shown.length ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {shown.map((f) => <FindingCard key={f.finding_id} f={f} />)}
            </div>
          ) : (
            <Empty icon="task_alt" title="No findings in this view" />
          )}
        </section>
      )}

      {tab === "sensors" && (
        <section className="space-y-4 animate-rise">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-ink-soft">
              Live readings, sampled every 30&nbsp;s. The shaded band is the supplied
              operating range — telemetry is shown here only, never used for reasoning.
            </p>
            <div className="flex gap-1 rounded-xl bg-canvas border border-line p-1">
              {[1, 6, 24].map((h) => (
                <button key={h} onClick={() => setHours(h)}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                    hours === h ? "bg-white text-brand-700 shadow-sm" : "text-ink-muted hover:text-ink"
                  }`}>
                  {h}h
                </button>
              ))}
            </div>
          </div>

          {!telemetry ? (
            <div className="card p-10 flex justify-center"><Spinner /></div>
          ) : (
            asset.subsystems.map((sub) => {
              const traces = sub.sensor_keys
                .map((k) => telemetry.sensors.find((t) => t.key === k))
                .filter(Boolean) as NonNullable<Telemetry["sensors"][number]>[];
              if (!traces.length) return null;
              return (
                <div key={sub.key} className="space-y-3">
                  <p className="eyebrow">{sub.display_name}</p>
                  <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                    {traces.map((t) => {
                      const breach = isBreaching(t);
                      const sev = worst(
                        findings.filter((f) => f.target_key === t.key).map((f) => f.severity),
                      );
                      const S = SEVERITY[breach ? "critical" : sev];
                      return (
                        <div key={t.key} className="card p-4">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm font-semibold truncate">
                                {prettySensor(t.key)}
                              </p>
                              <p className="mt-1 flex items-baseline gap-1">
                                <span className="num text-2xl font-bold tracking-tight">
                                  {t.latest ? t.latest.value : "—"}
                                </span>
                                <span className="num text-xs text-ink-muted">
                                  {t.unit_symbol}
                                </span>
                              </p>
                            </div>
                            <span className={`inline-flex items-center gap-1 rounded-full px-2
                                              py-0.5 text-[11px] font-semibold ring-1 ${S.pill}`}>
                              <Icon name={S.icon} className="text-[13px]" />
                              {breach ? "Out of range" : S.label}
                            </span>
                          </div>

                          <div className="mt-2">
                            <SensorChart sensor={t} hours={hours} />
                          </div>

                          <p className="mt-1 num text-[11px] text-ink-3">
                            {t.threshold
                              ? `limit ${t.threshold.low ?? "−∞"} – ${t.threshold.high ?? "∞"} ${t.unit_symbol}`
                              : "no supplied limit"}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })
          )}
        </section>
      )}

      {tab === "graph" && (
        <div className="card p-5 animate-rise">
          {graph?.nodes.length ? (
            <>
              <p className="text-sm text-ink-soft">
                <b className="num">{graph.nodes.length}</b> knowledge nodes and{" "}
                <b className="num">{graph.edges.length}</b> relationships — equipment,
                subsystems, sensors, thresholds and the finding-conditions observed on them.
                Telemetry is never stored here.
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(
                  (graph.nodes as { type: string }[]).reduce<Record<string, number>>((acc, n) => {
                    acc[n.type] = (acc[n.type] ?? 0) + 1;
                    return acc;
                  }, {}),
                ).map(([type, n], i) => (
                  <div key={type}
                    className="flex items-center justify-between rounded-xl bg-canvas
                               border border-line px-3 py-2.5">
                    <span className="flex items-center gap-2 text-sm font-medium capitalize">
                      <span className="h-2 w-2 rounded-full"
                        style={{ background: ["#7C3AED", "#0F9D8F", "#C026D3", "#4D7C0F", "#0284C7"][i % 5] }} />
                      {type.replace(/_/g, " ")}
                    </span>
                    <span className="num text-sm font-bold">{n}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Empty icon="graph_3" title="Graph not projected yet" />
          )}
        </div>
      )}

      {tab === "reports" && (
        reports.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {reports.map((r) => (
              <article key={r.report_id} className="card card-hover p-5 animate-rise">
                <div className="flex items-center justify-between">
                  <p className="eyebrow">{r.report_type.replace(/_/g, " ")}</p>
                  <span className="pill bg-brand-50 text-brand-700 ring-brand-200 capitalize">
                    {r.persona.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="mt-2 num text-2xl font-bold">
                  {String((r.payload as { finding_count?: number }).finding_count ?? "—")}
                  <span className="text-sm text-ink-muted font-medium ml-1">findings</span>
                </p>
                <p className="mt-2 text-xs text-ink-muted">
                  Cites {r.cited_finding_ids.length} finding ids · reproducible from the same evidence
                </p>
              </article>
            ))}
          </div>
        ) : <Empty icon="description" title="No reports yet" />
      )}

      {tab === "runs" && (
        runs.length ? (
          <div className="card overflow-hidden animate-rise">
            <table className="w-full text-sm">
              <thead className="bg-canvas border-b border-line">
                <tr className="text-left">
                  {["Run", "Status", "Findings", "Artifacts", "Input hash"].map((h) => (
                    <th key={h} className="eyebrow px-4 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id} className="border-b border-line last:border-0 hover:bg-canvas">
                    <td className="num px-4 py-3">{r.run_id.slice(0, 10)}</td>
                    <td className="px-4 py-3">
                      <span className="pill bg-ok-soft text-ok ring-ok-ring">
                        <Icon name="check_circle" className="text-[14px]" /> {r.status}
                      </span>
                    </td>
                    <td className="num px-4 py-3 font-semibold">{r.finding_count}</td>
                    <td className="num px-4 py-3 text-ink-muted">{r.artifact_ids.length}</td>
                    <td className="num px-4 py-3 text-ink-muted">{r.input_hash.slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty icon="history" title="No runs recorded" />
      )}
    </>
  );
}
