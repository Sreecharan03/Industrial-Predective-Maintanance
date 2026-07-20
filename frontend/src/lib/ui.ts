/** Presentation tokens. Status colour is ALWAYS paired with an icon + label —
 *  never colour alone (accessibility + the two closest status pairs sit at the
 *  dE ~11 floor, which is only legal with a secondary encoding). */

import type { Finding, Origin, Severity } from "./api";

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


/* ------------------------------------------------------------------ *
 *  Plain English
 *
 *  The engines write for precision ("42.63% of readings sit in runs of 5+
 *  identical"). An operator on the shop floor should not have to decode that.
 *  These helpers rewrite a finding into how a colleague would say it out loud,
 *  keeping the real numbers but dropping the vocabulary.
 *
 *  The precise engineering wording is never destroyed — it stays available
 *  under "the technical version" for anyone who wants it.
 * ------------------------------------------------------------------ */

/** Terms the engines use that nobody outside the platform says. */
const JARGON: [RegExp, string][] = [
  [/\bthreshold\b/gi, "limit"],
  [/\bsetpoint\b/gi, "safety limit"],
  [/protection (safety )?limit/gi, "safety cut-off"],
  [/\bbreached?\b/gi, "went past"],
  [/\bexceeds?\b/gi, "went past"],
  [/\bcritical state\b/gi, "unsafe level"],
  [/\bhypothesis\b/gi, "not confirmed yet"],
  [/\badvisory\b/gi, "for information"],
  [/\bdegradation\b/gi, "worsening"],
  [/\bdeviation\b/gi, "difference"],
  [/\banomal(y|ous)\b/gi, "unusual"],
  [/\bnovelty\b/gi, "unusual behaviour"],
  [/\bregimes?\b/gi, "running mode"],
  [/\bflatlined?\b/gi, "stuck on one value"],
  [/\bmis-?set\b/gi, "set wrongly"],
  [/\bP25-P75\b/g, "most of the time"],
  [/\binterval\b/gi, "range"],
  [/\bseasonal_naive\b/g, "recent-pattern"],
  [/\bETS\b/g, "trend"],
  [/\bMAE\b/g, "average error"],
  [/\bsubsystem\b/gi, "section"],
  [/\bequipment\b/gi, "machine"],
  [/\bsensor:/gi, ""],
  [/\bequipment:/gi, ""],
];

/** Strip identifiers and engine vocabulary out of any engine-written line. */
export function deJargon(text: string): string {
  let out = text;
  for (const [re, plain] of JARGON) out = out.replace(re, plain);
  // sensor keys -> readable names, e.g. discharge_pressure_com1
  out = out.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (m) => prettySensor(m).toLowerCase());
  return out.replace(/\s{2,}/g, " ").replace(/\(\s*\)/g, "").trim();
}

/** Sensor names read better lowercase inside a sentence ("discharge pressure has
 *  gone past…"), with only the sentence itself capitalised. */
const naming = (key: string): string => prettySensor(key).toLowerCase();
const sentence = (text: string): string =>
  text ? text.charAt(0).toUpperCase() + text.slice(1) : text;

const num = (v: unknown, dp = 1): string =>
  typeof v === "number" ? v.toFixed(dp).replace(/\.0$/, "") : String(v ?? "");

/** Pull a value out of a finding's evidence by a phrase in its description. */
function ev(f: Finding, needle: string): number | string | null {
  const hit = f.evidence.find((e) => e.description.toLowerCase().includes(needle));
  return hit ? hit.observed_value : null;
}

/** The headline, as a person would say it. Falls back to a de-jargoned summary
 *  for any finding type we have not written a sentence for. */
export function humanSummary(f: Finding): string {
  return sentence(summaryBody(f));
}

function summaryBody(f: Finding): string {
  const what = naming(f.target_key);
  switch (f.finding_type) {
    case "threshold_critical": {
      const v = ev(f, "current state") ?? ev(f, "value");
      return v !== null
        ? `${what} has gone past its safe limit — it is at ${num(v, 2)} right now`
        : `${what} has gone past its safe limit`;
    }
    case "health_degraded": {
      const score = ev(f, "health score");
      const where = f.scope === "equipment" ? "this machine" : `the ${what} section`;
      return score !== null
        ? `${where} is running at ${num(score)}% condition — below its normal`
        : `${where} is not in its usual condition`;
    }
    case "reliability_flatline":
      return `${what} keeps repeating the exact same number — the sensor may be stuck`;
    case "reliability_drift":
      return `${what} readings have slowly shifted over time — it may need recalibrating`;
    case "sensor_untrustworthy":
      return `${what} readings cannot be fully trusted at the moment`;
    case "threshold_misspecified":
    case "threshold_config_review_recommended":
      return `The limit set for ${what} does not match how this machine actually runs — the limit looks wrong, not the machine`;
    case "critical_on_untrustworthy_sensor":
      return `${what} shows a serious reading, but from a sensor we do not fully trust — check it before acting`;
    case "condenser_fouling_suspected":
      return "The condenser looks like it may be dirty or blocked";
    case "novelty_elevated": {
      const windows = Number(String(f.summary).match(/\d+/)?.[0] ?? 0);
      return windows
        ? `This machine has been behaving differently from its usual pattern (${windows} times recently)`
        : "This machine has been behaving differently from its usual pattern";
    }
    case "operating_regime_discovered": {
      const n = Number(String(f.summary).match(/\d+/)?.[0] ?? 0);
      return n
        ? `Spotted ${n} different ways this machine normally runs`
        : "Spotted the different ways this machine normally runs";
    }
    case "forecast_threshold_approach": {
      const bound = ev(f, "bound approached");
      const hours = ev(f, "lead-time steps");
      const when = typeof hours === "number"
        ? (hours <= 1 ? "within about an hour" : `in about ${num(hours)} hours`)
        : "soon";
      return bound !== null
        ? `If it keeps going this way, ${what} could reach ${num(bound, 2)} ${when}`
        : `If it keeps going this way, ${what} could reach its limit ${when}`;
    }
    default:
      return deJargon(f.summary);
  }
}

/** The supporting line: what makes us say that. */
export function humanDetail(f: Finding): string {
  return sentence(detailBody(f));
}

function detailBody(f: Finding): string {
  switch (f.finding_type) {
    case "health_degraded": {
      const parts = f.detail.split(";").map((p) => p.trim()).filter(Boolean);
      const names = parts
        .map((p) => naming(p.split(":")[0]?.trim() ?? ""))
        .filter(Boolean);
      return names.length
        ? `What is pulling it down: ${names.join(", ")}.`
        : deJargon(f.detail);
    }
    case "novelty_elevated": {
      const drivers = [...f.detail.matchAll(/([a-z0-9_]+)\s*\(([-+][\d.]+)\)/g)].map(
        ([, key, dev]) =>
          `${naming(key)} (${Number(dev) > 0 ? "higher" : "lower"} than usual)`,
      );
      return drivers.length
        ? `Mostly down to: ${drivers.join(", ")}. This is an early signal, not a fault.`
        : "This is an early signal, not a fault.";
    }
    case "reliability_flatline": {
      const pct = f.detail.match(/([\d.]+)%/)?.[1];
      return pct
        ? `About ${Math.round(Number(pct))}% of readings were the same number repeated back to back.`
        : deJargon(f.detail);
    }
    case "forecast_threshold_approach":
      return "This is a projection of the current trend, not something that has happened. Worth keeping an eye on.";
    case "operating_regime_discovered":
      return "Useful for knowing what normal looks like on this machine. Nothing is wrong.";
    case "threshold_misspecified":
    case "threshold_config_review_recommended":
      return "The machine has been running normally at these values, so the limit is likely due for review.";
    default:
      return deJargon(f.detail);
  }
}
