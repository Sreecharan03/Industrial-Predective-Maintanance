import { useEffect, useState } from "react";
import { api, type Feedback, type Verdict } from "../lib/api";
import { Icon } from "./ui";

/** Engineer triage on a learned hypothesis.
 *
 *  This is the label-capture step: each verdict here becomes a supervised
 *  training example later, so the wording asks what the engineer actually knows
 *  ("was this real?") rather than asking them to rate the model. */

const OPTIONS: { verdict: Verdict; label: string; icon: string; cls: string; help: string }[] = [
  {
    verdict: "confirmed_novelty",
    label: "Real",
    icon: "check_circle",
    cls: "text-ok ring-ok-ring hover:bg-ok-soft",
    help: "Something genuinely was unusual here",
  },
  {
    verdict: "expected_behaviour",
    label: "Expected",
    icon: "info",
    cls: "text-ink-soft ring-line hover:bg-canvas",
    help: "Unusual to the model, but normal for this machine",
  },
  {
    verdict: "false_positive",
    label: "Wrong",
    icon: "cancel",
    cls: "text-crit ring-crit-ring hover:bg-crit-soft",
    help: "The model was mistaken — nothing was happening",
  },
];

export function VerdictButtons({ identityKey }: { identityKey: string }) {
  const [history, setHistory] = useState<Feedback[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.feedbackHistory(identityKey)
      .then((h) => { if (alive) setHistory(h); })
      .catch(() => { if (alive) setHistory([]); });
    return () => { alive = false; };
  }, [identityKey]);

  const current = history?.length ? history[history.length - 1] : null;

  const submit = async (verdict: Verdict) => {
    setBusy(true);
    setError(null);
    try {
      await api.recordFeedback(identityKey, verdict);
      setHistory(await api.feedbackHistory(identityKey));
    } catch (e) {
      setError((e as Error).message || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 rounded-xl border border-line bg-canvas px-3.5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-bold tracking-[0.08em] uppercase text-ink-muted">
          Was this real?
        </p>
        {current && (
          <span className="text-[10.5px] text-ink-muted">
            {current.author} said <b>{OPTIONS.find((o) => o.verdict === current.verdict)?.label}</b>
            {history && history.length > 1 && ` · ${history.length} verdicts`}
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {OPTIONS.map((o) => {
          const active = current?.verdict === o.verdict;
          return (
            <button
              key={o.verdict}
              disabled={busy}
              onClick={() => submit(o.verdict)}
              title={o.help}
              className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px]
                          font-bold ring-1 transition-colors disabled:opacity-50
                          ${active ? "bg-ink text-white ring-ink" : `bg-card ${o.cls}`}`}
            >
              <Icon name={o.icon} className="text-[15px]" />
              {o.label}
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-[10.5px] text-ink-muted leading-snug">
        Your answer is stored as a training label — this is how the system learns which
        signals are worth raising.
      </p>
      {error && <p className="mt-1 text-[10.5px] text-crit">{error}</p>}
    </div>
  );
}
