/** Presentation tokens. Status colour is ALWAYS paired with an icon + label —
 *  never colour alone (accessibility + the two closest status pairs sit at the
 *  dE ~11 floor, which is only legal with a secondary encoding). */

import type { Origin, Severity } from "./api";

export const CATEGORICAL = ["#7C3AED", "#0F9D8F", "#C026D3", "#4D7C0F", "#0284C7"];

export const SEVERITY: Record<
  Severity,
  { label: string; icon: string; pill: string; dot: string; text: string }
> = {
  ok: {
    label: "Healthy", icon: "check_circle",
    pill: "bg-ok-soft text-ok ring-ok-ring", dot: "bg-ok", text: "text-ok",
  },
  info: {
    label: "Info", icon: "info",
    pill: "bg-info-soft text-info ring-info-ring", dot: "bg-info", text: "text-info",
  },
  warning: {
    label: "Watch", icon: "warning",
    pill: "bg-warn-soft text-warn ring-warn-ring", dot: "bg-warn", text: "text-warn",
  },
  critical: {
    label: "Critical", icon: "e911_emergency",
    pill: "bg-crit-soft text-crit ring-crit-ring", dot: "bg-crit", text: "text-crit",
  },
};

export const ORIGIN: Record<Origin, { label: string; hint: string; pill: string }> = {
  derived: {
    label: "Fact",
    hint: "Deterministic — measured and computed.",
    pill: "bg-brand-50 text-brand-700 ring-brand-200",
  },
  diagnosed: {
    label: "Diagnosis",
    hint: "Rule-derived, carries rule confidence.",
    pill: "bg-[#E7F6F4] text-[#0B7A6E] ring-[#B7E4DE]",
  },
  learned: {
    label: "Hypothesis",
    hint: "Learned / forecast — advisory, unconfirmed.",
    pill: "bg-[#FBEAFE] text-[#9A1FAB] ring-[#F0C4F7]",
  },
};

export const CLASSES: Record<
  string,
  { slug: string; label: string; icon: string; blurb: string }
> = {
  refrigeration_screw_compressor: {
    slug: "refrigeration", label: "Refrigeration", icon: "ac_unit",
    blurb: "Screw compressors / chillers",
  },
  utility_air_compressor: {
    slug: "air-compressors", label: "Air Compressors", icon: "compress",
    blurb: "Utility air compressors",
  },
  nitrogen_psa_plant: {
    slug: "nitrogen", label: "Nitrogen Plant", icon: "airwave",
    blurb: "N₂ PSA generation",
  },
};

export const SLUG_TO_CLASS: Record<string, string> = Object.fromEntries(
  Object.entries(CLASSES).map(([k, v]) => [v.slug, k]),
);

/** Worst severity present, for a fleet/asset roll-up. */
const RANK: Severity[] = ["ok", "info", "warning", "critical"];
export function worst(severities: Severity[]): Severity {
  return severities.reduce<Severity>(
    (acc, s) => (RANK.indexOf(s) > RANK.indexOf(acc) ? s : acc),
    "ok",
  );
}

/** A health score in 0..100 derived from what the platform actually knows:
 *  the mix and severity of its findings. No invented failure probability. */
export function healthScore(severities: Severity[]): number {
  if (!severities.length) return 100;
  const penalty = { ok: 0, info: 2, warning: 9, critical: 26 };
  const total = severities.reduce((s, v) => s + penalty[v], 0);
  return Math.max(0, Math.min(100, Math.round(100 - total)));
}

export function prettySensor(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
