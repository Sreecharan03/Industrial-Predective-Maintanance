import { Link, useParams } from "react-router-dom";
import { useFleet } from "../lib/useFleet";
import { CLASSES, SEVERITY, SLUG_TO_CLASS } from "../lib/ui";
import { Empty, HealthRing, Icon, Spinner, StatusPill } from "../components/ui";

export default function Fleet() {
  const { slug = "" } = useParams();
  const cls = SLUG_TO_CLASS[slug];
  const meta = CLASSES[cls];
  const { assets, error } = useFleet();

  if (error) return <Empty icon="cloud_off" title="Cannot reach the platform" hint={error} />;
  if (!assets) return <Spinner label="Loading fleet…" />;

  const group = assets.filter((a) => a.equipment_class === cls);

  return (
    <>
      <header className="animate-rise">
        <div className="flex items-center gap-2 text-ink-muted">
          <Icon name={meta?.icon ?? "memory"} className="text-[20px]" />
          <span className="eyebrow">{meta?.blurb ?? "Fleet"}</span>
        </div>
        <h1 className="mt-1 text-2xl lg:text-3xl font-extrabold tracking-tight">
          {meta?.label ?? slug}
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          {group.length} asset{group.length === 1 ? "" : "s"} monitored
        </p>
      </header>

      {!group.length ? (
        <Empty
          icon="precision_manufacturing"
          title="No assets analysed in this group yet"
          hint="Run an analysis to populate it."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {group.map((a) => (
            <Link key={a.unit} to={`/asset/${encodeURIComponent(a.unit)}`}
              className="card card-hover p-6 group animate-rise">
              <div className="flex items-start gap-5">
                <HealthRing score={a.health} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-bold text-xl tracking-tight truncate">{a.unit}</p>
                    <StatusPill severity={a.severity} />
                  </div>

                  <dl className="mt-4 grid grid-cols-3 gap-3">
                    {[
                      { k: "Findings", v: a.findings.length, i: "fact_check" },
                      { k: "Diagnoses", v: a.diagnoses, i: "clinical_notes" },
                      { k: "Sensors", v: a.sensor_count, i: "sensors" },
                    ].map((s) => (
                      <div key={s.k} className="rounded-xl bg-canvas border border-line p-2.5">
                        <dt className="eyebrow flex items-center gap-1">
                          <Icon name={s.i} className="text-[13px]" /> {s.k}
                        </dt>
                        <dd className="num mt-1 text-lg font-bold">{s.v}</dd>
                      </div>
                    ))}
                  </dl>

                  <div className="mt-4 flex gap-[2px] h-1.5">
                    {(["critical", "warning", "info", "ok"] as const).map((s) => {
                      const n = a.findings.filter((f) => f.severity === s).length;
                      if (!n) return null;
                      return (
                        <span key={s} title={`${n} ${SEVERITY[s].label}`}
                          className={`${SEVERITY[s].dot} rounded-full`} style={{ flex: n }} />
                      );
                    })}
                    {!a.findings.length && <span className="flex-1 rounded-full bg-line" />}
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
