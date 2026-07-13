import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Report } from "../lib/api";
import { useFleet } from "../lib/useFleet";
import { Empty, Icon, Spinner } from "../components/ui";

export default function Reports() {
  const { assets } = useFleet();
  const [reports, setReports] = useState<(Report & { _unit: string })[] | null>(null);

  useEffect(() => {
    if (!assets) return;
    Promise.all(
      assets.map((a) =>
        api.reports(a.unit)
          .then((rs) => rs.map((r) => ({ ...r, _unit: a.unit })))
          .catch(() => []),
      ),
    ).then((all) => setReports(all.flat()));
  }, [assets]);

  if (!reports) return <Spinner label="Loading reports…" />;

  return (
    <>
      <header className="animate-rise">
        <span className="eyebrow">Documents</span>
        <h1 className="mt-1 text-2xl lg:text-3xl font-extrabold tracking-tight">Reports</h1>
        <p className="mt-1 text-sm text-ink-muted max-w-2xl">
          Generated from the same grounded evidence — rebuilding a report from the same
          findings reproduces it exactly.
        </p>
      </header>

      {reports.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {reports.map((r) => (
            <Link key={r.report_id} to={`/asset/${encodeURIComponent(r._unit)}`}
              className="card card-hover p-5 animate-rise">
              <div className="flex items-start justify-between gap-2">
                <span className="h-9 w-9 rounded-xl bg-brand-50 text-brand-600 grid place-items-center">
                  <Icon name="description" className="text-[18px]" />
                </span>
                <span className="pill bg-info-soft text-info ring-info-ring capitalize">
                  {r.persona.replace(/_/g, " ")}
                </span>
              </div>
              <p className="mt-3 font-bold tracking-tight">{r._unit}</p>
              <p className="text-xs text-ink-muted capitalize">
                {r.report_type.replace(/_/g, " ")}
              </p>
              <div className="mt-4 flex items-center justify-between">
                <span className="num text-2xl font-bold">
                  {String((r.payload as { finding_count?: number }).finding_count ?? "—")}
                </span>
                <span className="text-xs text-ink-muted">
                  {r.cited_finding_ids.length} citations
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Empty icon="description" title="No reports yet"
          hint="A summary is saved each time the machine is checked." />
      )}
    </>
  );
}
