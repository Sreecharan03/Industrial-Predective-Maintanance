import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type GroundedAnswer } from "../lib/api";
import { useFleet } from "../lib/useFleet";
import { Empty, Icon, Spinner } from "../components/ui";

const PERSONAS = [
  { id: "operator", label: "Operator" },
  { id: "maintenance_engineer", label: "Maintenance" },
  { id: "reliability_engineer", label: "Reliability" },
  { id: "plant_manager", label: "Plant Manager" },
  { id: "executive", label: "Executive" },
];

const CATEGORY: Record<string, { label: string; cls: string }> = {
  fact: { label: "Fact", cls: "bg-brand-50 text-brand-700 ring-brand-200" },
  diagnosis: { label: "Diagnosis", cls: "bg-[#E7F6F4] text-[#0B7A6E] ring-[#B7E4DE]" },
  hypothesis: { label: "Hypothesis", cls: "bg-[#FBEAFE] text-[#9A1FAB] ring-[#F0C4F7]" },
  forecast: { label: "Forecast", cls: "bg-warn-soft text-warn ring-warn-ring" },
};

const SUGGESTIONS = [
  "Is this asset healthy?",
  "Are any operating limits being approached?",
  "What should maintenance look at first?",
  "Why were these thresholds flagged?",
];

interface Turn { q: string; a: GroundedAnswer | null; error?: string }

export default function Copilot() {
  const [params] = useSearchParams();
  const { assets } = useFleet();
  const [unit, setUnit] = useState(params.get("unit") ?? "");
  const [persona, setPersona] = useState("reliability_engineer");
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!unit && assets?.length) setUnit(assets[0].unit);
  }, [assets, unit]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, busy]);

  const ask = async (question: string) => {
    if (!question.trim() || !unit || busy) return;
    setQ("");
    setBusy(true);
    setTurns((t) => [...t, { q: question, a: null }]);
    try {
      // Send the conversation so far, so follow-ups like "what do you mean?" work.
      // Evidence is still re-retrieved fresh each turn — memory only shapes wording.
      const history = turns
        .filter((t) => t.a)
        .flatMap((t) => [
          { role: "user" as const, content: t.q },
          { role: "assistant" as const, content: t.a!.answer },
        ])
        .slice(-6);
      const a = await api.ask(unit, question, persona, history);
      setOffline(a.model === "stub");
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
    } catch (e) {
      setTurns((t) =>
        t.map((x, i) => (i === t.length - 1 ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <header className="animate-rise">
        <span className="eyebrow">Grounded assistant</span>
        <h1 className="mt-1 text-2xl lg:text-3xl font-extrabold tracking-tight">Plant Copilot</h1>
        <p className="mt-1 text-sm text-ink-muted max-w-2xl">
          It can only say what the evidence supports. Every engineering claim cites a finding id —
          anything unsupported is dropped, and gaps are stated as{" "}
          <b className="text-ink">insufficient evidence</b>.
        </p>
      </header>

      {offline && (
        <div className="card mt-4 flex items-start gap-3 border-warn-ring bg-warn-soft p-4">
          <Icon name="cloud_off" className="mt-0.5 text-warn" />
          <div className="text-sm">
            <p className="font-semibold text-warn">Copilot is in offline mode</p>
            <p className="mt-0.5 text-ink-soft">
              No language model is configured, so it can only list the evidence rather than
              hold a conversation. Set <code className="num">SENSEMINDS_GROQ_API_KEY</code> and
              restart the API.
            </p>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <select value={unit} onChange={(e) => setUnit(e.target.value)}
          className="rounded-xl border border-line bg-card px-3 py-2 text-sm font-semibold
                     outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-50">
          {assets?.map((a) => <option key={a.unit} value={a.unit}>{a.unit}</option>) ?? (
            <option>Loading…</option>
          )}
        </select>
        <div className="flex flex-wrap gap-1.5">
          {PERSONAS.map((p) => (
            <button key={p.id} onClick={() => setPersona(p.id)}
              className={`pill ring-1 ${
                persona === p.id
                  ? "bg-brand-600 text-white ring-brand-600"
                  : "bg-card text-ink-soft ring-line hover:bg-canvas"
              }`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Conversation */}
      <div className="space-y-4 min-h-[240px]">
        {!turns.length && (
          <div className="card p-8 text-center animate-rise">
            <span className="h-12 w-12 rounded-2xl bg-brand-50 text-brand-600 grid place-items-center mx-auto">
              <Icon name="auto_awesome" />
            </span>
            <p className="mt-4 font-semibold">Ask about {unit || "an asset"}</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => ask(s)} className="btn-quiet text-xs">{s}</button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[80%] rounded-2xl rounded-br-md bg-brand-600 text-white
                            px-4 py-2.5 text-sm font-medium shadow-soft animate-rise">
                {t.q}
              </p>
            </div>

            {t.error && (
              <p className="pill bg-crit-soft text-crit ring-crit-ring">
                <Icon name="error" className="text-[14px]" /> {t.error}
              </p>
            )}

            {!t.a && !t.error && <Spinner label="Looking at the readings…" />}

            {t.a && (
              <article className="card p-5 animate-rise">
                <p className="text-[15px] leading-relaxed">{t.a.answer}</p>

                {t.a.claims.length > 0 && (
                  <div className="mt-5">
                    <p className="eyebrow">Grounded claims · each cites its evidence</p>
                    <ul className="mt-2 space-y-2">
                      {t.a.claims.map((c, j) => {
                        const cat = CATEGORY[c.category] ?? CATEGORY.fact;
                        return (
                          <li key={j}
                            className="rounded-xl bg-canvas border border-line p-3 flex gap-3">
                            <span className={`pill shrink-0 h-fit ${cat.cls}`}>{cat.label}</span>
                            <div className="min-w-0">
                              <p className="text-sm leading-snug">{c.text}</p>
                              <p className="mt-1 flex flex-wrap gap-1">
                                {c.citations.map((id) => (
                                  <span key={id}
                                    className="num text-[10px] text-ink-muted bg-card border
                                               border-line rounded px-1.5 py-0.5">
                                    {id.slice(0, 10)}
                                  </span>
                                ))}
                              </p>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                {t.a.insufficient.length > 0 && (
                  <div className="mt-4 rounded-xl bg-warn-soft ring-1 ring-warn-ring p-3">
                    <p className="flex items-center gap-1.5 text-xs font-bold text-warn uppercase tracking-wide">
                      <Icon name="help" className="text-[15px]" /> Insufficient evidence
                    </p>
                    <ul className="mt-1.5 space-y-0.5">
                      {t.a.insufficient.map((s, j) => (
                        <li key={j} className="text-sm text-ink-soft">· {s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </article>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>

      {/* Composer */}
      <form onSubmit={(e) => { e.preventDefault(); ask(q); }}
        className="sticky bottom-4 flex gap-2 card p-2 shadow-lift">
        <input
          value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={`Ask about ${unit || "an asset"}…`}
          className="flex-1 bg-transparent px-3 py-2 text-sm outline-none"
        />
        <button className="btn-primary" disabled={busy || !q.trim()}>
          <Icon name="send" className="text-[18px]" />
          <span className="hidden sm:inline">Ask</span>
        </button>
      </form>
    </>
  );
}
