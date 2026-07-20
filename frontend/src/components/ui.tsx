import { useState } from "react";
import type { ReactNode } from "react";
import type { Finding, Severity } from "../lib/api";
import { ORIGIN, SEVERITY, humanDetail, humanSummary, prettySensor } from "../lib/ui";
import { VerdictButtons } from "./VerdictButtons";

export function Icon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <span className={`icon select-none ${className}`} aria-hidden="true">
      {name}
    </span>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-ink-muted text-sm py-14 justify-center">
      <span className="h-4 w-4 rounded-full border-2 border-line border-t-brand-600 animate-spin" />
      {label}
    </div>
  );
}

export function Empty({ icon = "inbox", title, hint }: { icon?: string; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="h-12 w-12 rounded-2xl bg-canvas border border-line grid place-items-center text-ink-muted">
        <Icon name={icon} />
      </div>
      <p className="mt-4 font-semibold text-ink">{title}</p>
      {hint && <p className="mt-1 text-sm text-ink-muted max-w-sm">{hint}</p>}
    </div>
  );
}

export function StatusPill({ severity }: { severity: Severity }) {
  const s = SEVERITY[severity];
  return (
    <span className={`pill ${s.pill}`}>
      <Icon name={s.icon} className="text-[14px]" />
      {s.label}
    </span>
  );
}

export function OriginPill({ origin }: { origin: Finding["origin"] }) {
  const o = ORIGIN[origin];
  return (
    <span className={`pill ${o.pill}`} title={o.hint}>
      {o.label}
    </span>
  );
}

export function Section({
  title, subtitle, action, children,
}: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="animate-rise">
      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          {subtitle && <p className="text-sm text-ink-muted mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A headline number. The most important thing on the card is the value. */
export function StatCard({
  label, value, unit, icon, tone = "brand", foot,
}: {
  label: string; value: string | number; unit?: string; icon: string;
  tone?: "brand" | "ok" | "warn" | "crit" | "info"; foot?: ReactNode;
}) {
  const tones: Record<string, string> = {
    brand: "bg-brand-50 text-brand-600",
    ok: "bg-ok-soft text-ok",
    warn: "bg-warn-soft text-warn",
    crit: "bg-crit-soft text-crit",
    info: "bg-info-soft text-info",
  };
  return (
    <div className="card card-hover p-5 animate-rise">
      <div className="flex items-start justify-between">
        <p className="eyebrow">{label}</p>
        <span className={`h-8 w-8 rounded-xl grid place-items-center ${tones[tone]}`}>
          <Icon name={icon} className="text-[18px]" />
        </span>
      </div>
      <p className="mt-3 flex items-baseline gap-1">
        <span className="num text-3xl font-bold">{value}</span>
        {unit && <span className="text-sm text-ink-muted font-medium">{unit}</span>}
      </p>
      {foot && <div className="mt-2 text-xs text-ink-muted">{foot}</div>}
    </div>
  );
}

/** Health as a thin arc — magnitude, so a single hue ramp, not a rainbow. */
export function HealthRing({ score, size = 92 }: { score: number; size?: number }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const tone = score >= 85 ? "#15803D" : score >= 60 ? "#B45309" : "#BE123C";
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#EDE9E6" strokeWidth="7" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone} strokeWidth="7"
          strokeLinecap="round" strokeDasharray={c}
          strokeDashoffset={c - (c * score) / 100}
          style={{ transition: "stroke-dashoffset .9s cubic-bezier(.22,.9,.3,1)" }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="num text-xl font-bold leading-none">{score}</div>
        <div className="text-[9px] font-bold uppercase tracking-wider text-ink-muted mt-0.5">
          health
        </div>
      </div>
    </div>
  );
}

export function FindingCard({ f, onCite }: { f: Finding; onCite?: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [tech, setTech] = useState(false);   // the engineering wording, on request

  return (
    <article className="card card-hover p-4 animate-rise">
      <div className="flex items-start gap-3">
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY[f.severity].dot}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill severity={f.severity} />
            <OriginPill origin={f.origin} />
            <span className="text-xs text-ink-muted font-medium">
              {prettySensor(f.target_key)}
            </span>
          </div>

          {/* Plain English first — what this actually means. */}
          <p className="mt-2 font-semibold text-[15px] leading-snug">
            {humanSummary(f)}
          </p>

          <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
            <span className="inline-flex items-center gap-1">
              <Icon name="verified" className="text-[14px]" />
              <b className="num text-ink-soft">{(f.confidence.value * 100).toFixed(0)}%</b> sure
            </span>
            <button
              onClick={() => setOpen((o) => !o)}
              className="inline-flex items-center gap-1 font-medium hover:text-brand-600 transition-colors"
            >
              <Icon name={open ? "expand_less" : "expand_more"} className="text-[15px]" />
              {open ? "Hide details" : "Details"}
            </button>
          </div>

          {open && (
            <div className="mt-3 rounded-xl bg-canvas border border-line p-3 space-y-2">
              <p className="text-sm text-ink-soft leading-relaxed">{humanDetail(f)}</p>

              {/* The engines' exact wording stays available - simplified for
                  reading, never hidden from anyone who wants the precise text. */}
              <button
                onClick={() => setTech((t) => !t)}
                className="text-[11px] font-medium text-ink-muted hover:text-brand-600
                           inline-flex items-center gap-1 transition-colors"
              >
                <Icon name={tech ? "unfold_less" : "unfold_more"} className="text-[13px]" />
                {tech ? "Hide the technical version" : "Show the technical version"}
              </button>
              {tech && (
                <div className="rounded-lg bg-card border border-line px-3 py-2 space-y-1">
                  <p className="text-[12px] font-medium leading-snug">{f.summary}</p>
                  <p className="text-[12px] text-ink-muted leading-relaxed">{f.detail}</p>
                </div>
              )}
              {/* Learned findings are hypotheses — an engineer's verdict on them is
                  what turns this platform into a self-improving one. */}
              {f.origin === "learned" && <VerdictButtons identityKey={f.identity_key} />}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-[11px] text-ink-3">
                <span>checked by {f.source_engine}</span>
                <button
                  onClick={() => onCite?.(f.finding_id)}
                  className="num inline-flex items-center gap-1 hover:text-brand-600 transition-colors"
                  title="Reference id"
                >
                  <Icon name="tag" className="text-[13px]" />
                  {f.finding_id.slice(0, 10)}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

