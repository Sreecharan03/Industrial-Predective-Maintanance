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
    label: "Measured",
    hint: "Taken straight from the sensor readings.",
    pill: "bg-brand-50 text-brand-700 ring-brand-200",
  },
  diagnosed: {
    label: "Likely cause",
    hint: "Worked out from the readings.",
    pill: "bg-[#E7F6F4] text-[#0B7A6E] ring-[#B7E4DE]",
  },
  learned: {
    label: "Early signal",
    hint: "A pattern worth watching — not confirmed.",
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


/** What each finding actually MEANS, in plain English. The engines speak
 *  precisely; operators should not have to. */
export const PLAIN: Record<string, string> = {
  threshold_misspecified:
    "The limit set for this sensor doesn't match how the machine actually runs. The limit probably needs reviewing — this is not a fault.",
  threshold_config_review_recommended:
    "Worth reviewing this limit — it doesn't reflect how the machine normally operates.",
  threshold_critical:
    "A reading has gone past a safety limit. This needs attention now.",
  health_degraded:
    "Overall condition is below normal for this machine.",
  reliability_drift:
    "This sensor's readings have slowly shifted over time. It may need calibration.",
  reliability_flatline:
    "This sensor has been stuck on the same value — it may not be reporting properly.",
  sensor_untrustworthy:
    "This sensor's readings can't be fully trusted right now.",
  critical_on_untrustworthy_sensor:
    "A critical reading came from a sensor we don't fully trust — check it before acting.",
  condenser_fouling_suspected:
    "The condenser may be dirty or blocked.",
  novelty_elevated:
    "The machine is behaving unlike its usual pattern. An early signal, not confirmed.",
  operating_regime_discovered:
    "A distinct running mode was spotted in the data.",
  forecast_threshold_approach:
    "If the current trend continues, this reading could reach its limit soon. Advisory only.",
};

export const plainMeaning = (findingType: string): string | null =>
  PLAIN[findingType] ?? null;
