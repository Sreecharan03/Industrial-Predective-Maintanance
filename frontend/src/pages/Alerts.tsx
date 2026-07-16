import { useCallback, useEffect, useState } from "react";
import { api, type Alert } from "../lib/api";
import { plainMeaning } from "../lib/ui";
import { Empty, Icon, Spinner } from "../components/ui";

/* What each lifecycle stage / delivery outcome means, in plain English. */
const KIND: Record<Alert["kind"], { label: string; icon: string; cls: string }> = {
  triggered: { label: "Critical", icon: "emergency_home", cls: "text-crit bg-crit-soft ring-crit-ring" },
  reminder: { label: "Still critical", icon: "notification_important", cls: "text-warn bg-warn-soft ring-warn-ring" },
  resolved: { label: "Resolved", icon: "check_circle", cls: "text-ok bg-ok-soft ring-ok-ring" },
};

const STATUS: Record<Alert["status"], { label: string; hint: string; icon: string; cls: string }> = {
  sent: { label: "Email sent", hint: "Delivered to the escalation inbox", icon: "mark_email_read", cls: "text-ok" },
  pending: { label: "Sending…", hint: "Queued — will retry until delivered", icon: "schedule_send", cls: "text-ink-muted" },
  failed: { label: "Email failed", hint: "Gave up after 5 attempts — check SMTP", icon: "cancel_schedule_send", cls: "text-crit" },
  suppressed: { label: "Muted (flapping)", hint: "Re-triggered too soon after resolving — recorded, deliberately not emailed", icon: "notifications_paused", cls: "text-ink-muted" },
  skipped: { label: "No email set up", hint: "Recorded, but SMTP is not configured", icon: "unsubscribe", cls: "text-warn" },
};

function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function AlertCard({ a }: { a: Alert }) {
  const [open, setOpen] = useState(false);
  const kind = KIND[a.kind];
  const status = STATUS[a.status];
  const meaning = a.payload.finding_type ? plainMeaning(a.payload.finding_type) : null;

  return (
    <div className="card p-0 overflow-hidden animate-rise">
      <button onClick={() => setOpen(!open)} className="w-full text-left px-5 py-4 flex items-start gap-4">
        <span className={`mt-0.5 inline-flex items-center gap-1.5 shrink-0 rounded-full px-2.5 py-1
                          text-xs font-bold ring-1 ${kind.cls}`}>
          <Icon name={kind.icon} className="text-[15px]" />
          {kind.label}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold truncate">
            {a.payload.display_name ?? a.unit}
            <span className="text-ink-muted font-medium"> — {a.payload.summary ?? a.subject}</span>
          </p>
          <p className="mt-0.5 text-[12px] text-ink-muted">
            {ago(a.created_at)} · {a.payload.target_key ?? a.unit}
          </p>
        </div>
        <span className={`inline-flex items-center gap-1.5 shrink-0 text-xs font-semibold ${status.cls}`}
              title={status.hint}>
          <Icon name={status.icon} className="text-[16px]" />
          {status.label}
        </span>
        <Icon name={open ? "expand_less" : "expand_more"} className="text-ink-muted mt-0.5" />
      </button>

      {open && (
        <div className="px-5 pb-4 border-t border-line pt-3 space-y-3">
          {meaning && (
            <p className="text-[13px] text-ink-soft bg-canvas rounded-xl px-3.5 py-2.5">
              <b>What this means:</b> {meaning}
            </p>
          )}
          {a.payload.detail && <p className="text-[13px] text-ink-soft">{a.payload.detail}</p>}
          {!!a.payload.evidence?.length && (
            <div className="text-[12px] space-y-1">
              {a.payload.evidence.map((e, i) => (
                <div key={i} className="flex justify-between gap-4">
                  <span className="text-ink-muted">{e.description}</span>
                  <span className="font-bold tabular-nums">{e.observed_value ?? "—"}</span>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-ink-muted pt-1">
            <span title={status.hint}>Delivery: {status.hint}</span>
            {a.attempts > 0 && <span>{a.attempts} attempt{a.attempts !== 1 ? "s" : ""}</span>}
            {a.sent_at && <span>sent {ago(a.sent_at)}</span>}
            {a.last_error && <span className="text-crit">last error: {a.last_error}</span>}
            <span className="font-mono">finding {a.finding_id.slice(0, 16)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | Alert["kind"]>("all");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const load = useCallback(() => {
    api.alerts(200).then(setAlerts).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000); // follow the 30-second live loop
    return () => clearInterval(t);
  }, [load]);

  const sendTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.testAlert();
      setTestResult(`Test email accepted for ${r.to.join(", ")}`);
    } catch (e) {
      setTestResult(`Test failed: ${(e as Error).message}`);
    } finally {
      setTesting(false);
    }
  };

  if (error) return <Empty icon="cloud_off" title="Cannot reach the platform" hint={error} />;
  if (!alerts) return <Spinner label="Loading alerts…" />;

  const shown = alerts.filter((a) => filter === "all" || a.kind === filter);

  return (
    <>
      <header className="animate-rise flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="eyebrow">Escalation</span>
          <h1 className="mt-1 text-2xl lg:text-3xl font-extrabold tracking-tight">Alerts</h1>
          <p className="mt-1 text-sm text-ink-muted max-w-2xl">
            When a machine crosses a safety limit, an email goes to the escalation inbox —
            once when it happens, again if nobody deals with it, and once more when it clears.
            Everything is recorded here, including alerts that were deliberately not emailed.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <button onClick={sendTest} disabled={testing}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-600 text-white
                       text-sm font-bold px-4 py-2.5 shadow-soft hover:bg-brand-700
                       disabled:opacity-50 transition-colors">
            <Icon name={testing ? "hourglass_top" : "outgoing_mail"} className="text-[18px]" />
            {testing ? "Sending…" : "Send test email"}
          </button>
          {testResult && (
            <p className={`text-[11px] font-semibold ${
              testResult.startsWith("Test failed") ? "text-crit" : "text-ok"}`}>
              {testResult}
            </p>
          )}
        </div>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {(["all", "triggered", "reminder", "resolved"] as const).map((k) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`pill ring-1 ${
              filter === k
                ? "bg-ink text-white ring-ink"
                : "bg-card text-ink-soft ring-line hover:bg-canvas"
            }`}>
            {k === "all" ? `All (${alerts.length})` : KIND[k].label}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <Empty icon="notifications_off" title="No alerts yet"
          hint="Alerts appear the moment a machine crosses a safety limit." />
      ) : (
        <div className="space-y-3">
          {shown.map((a) => <AlertCard key={a.alert_id} a={a} />)}
        </div>
      )}
    </>
  );
}
