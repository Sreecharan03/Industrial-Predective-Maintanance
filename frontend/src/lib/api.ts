/** Typed client for the SenseMinds 360 REST API. */

const BASE = "/api/v1";
const TOKEN_KEY = "sm.token";

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  set(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
};

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (auth.token) headers.set("Authorization", `Bearer ${auth.token}`);
  if (init.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    auth.clear();
    window.location.hash = "#/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) throw new ApiError(res.status, (await res.text()) || res.statusText);
  return res.json() as Promise<T>;
}

/* ----------------------------- domain types ---------------------------- */

export type Severity = "ok" | "info" | "warning" | "critical";
export type Origin = "derived" | "diagnosed" | "learned";

export interface Evidence {
  artifact_id: string;
  description: string;
  observed_value: number | string | null;
}

export interface Finding {
  finding_id: string;
  identity_key: string;
  finding_type: string;
  category: string;
  scope: string;
  origin: Origin;
  summary: string;
  detail: string;
  target_key: string;
  equipment_key: string;
  subsystem_key: string | null;
  severity: Severity;
  confidence: { value: number; rationale: string };
  evidence: Evidence[];
  source_engine: string;
  observed_window: { start: string | null; end: string | null };
  triggered_by: string[];
}

export interface Sensor {
  key: string;
  display_name: string;
  sensor_type: string;
  unit: { symbol: string; assumed: boolean };
}

export interface AssetSummary {
  unit: string;
  equipment_class: string;
  display_name: string;
  sensor_count: number;
}

export interface Asset extends AssetSummary {
  sensors: Sensor[];
  subsystems: { key: string; display_name: string; sensor_keys: string[] }[];
}

export interface GraphNode {
  id: string;
  type: string;
  properties: Record<string, unknown>;
}
export interface GraphEdge {
  src: string;
  dst: string;
  type: string;
  properties: Record<string, unknown>;
}

export interface Report {
  report_id: string;
  report_type: string;
  persona: string;
  unit: string;
  requested_at: string;
  cited_finding_ids: string[];
  payload: Record<string, unknown>;
}

export interface EngineRun {
  run_id: string;
  unit: string;
  input_hash: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  finding_count: number;
  artifact_ids: string[];
}

export interface Alert {
  alert_id: string;
  unit: string;
  identity_key: string;
  finding_id: string;
  kind: "triggered" | "reminder" | "resolved";
  severity: Severity;
  subject: string;
  payload: {
    display_name?: string;
    finding_type?: string;
    summary?: string;
    detail?: string;
    target_key?: string;
    subsystem_key?: string | null;
    detected_at?: string;
    evidence?: { description: string; observed_value: number | string | null }[];
  };
  status: "pending" | "sent" | "failed" | "suppressed" | "skipped";
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export type Verdict = "confirmed_novelty" | "expected_behaviour" | "false_positive";

export interface Feedback {
  feedback_id: string;
  identity_key: string;
  finding_id: string;
  unit: string;
  verdict: Verdict;
  author: string;
  note: string;
  created_at: string;
}

export interface LabelProgress {
  labelled_conditions: number;
  total_verdicts: number;
  contributors: number;
  units_covered: number;
  by_verdict: Record<string, number>;
  target: number;
  percent_to_target: number;
  phase_c_ready: boolean;
}

export interface ForecastOutlook {
  sensor: string;
  hours_ahead: number;
  bound: number | null;
  projected_value: number | null;
  model_name: string;
  model_version: string;
  backtest_mae: number | null;
  interval_confidence: number;
  summary: string;
  finding_id: string;
}

export interface Outlook {
  unit: string;
  display_name: string;
  condition_score: number | null;
  condition_basis: string;
  weakest_subsystem: { key: string; score: number } | null;
  soonest: ForecastOutlook | null;
  forecasts: ForecastOutlook[];
  novelty: {
    score: number;
    windows: number;
    top_features: { feature: string; deviation: number }[];
    model_name: string;
    finding_id: string;
  } | null;
  critical_count: number;
  headline: string;
  caveat: string;
  recommendation: string;
  recommendation_citations: string[];
}

export interface SensorPoint { t: string; v: number }
export interface SensorTrace {
  key: string;
  display_name: string;
  unit_symbol: string;
  latest: { time: string; value: number } | null;
  threshold: { low: number | null; high: number | null } | null;
  points: SensorPoint[];
}
export interface Telemetry { unit: string; hours: number; sensors: SensorTrace[] }

export interface GroundedClaim {
  text: string;
  category: "fact" | "diagnosis" | "hypothesis" | "forecast";
  citations: string[];
}

export interface Turn { role: "user" | "assistant"; content: string }

export interface GroundedAnswer {
  unit: string;
  persona: string;
  answer: string;
  claims: GroundedClaim[];
  insufficient: string[];
  citations: string[];
}

/* -------------------------------- calls -------------------------------- */

export const api = {
  async login(username: string, password: string) {
    const body = new URLSearchParams({ username, password });
    const res = await fetch(`${BASE}/auth/token`, { method: "POST", body });
    if (!res.ok) throw new ApiError(res.status, "Incorrect employee ID or password");
    const data = (await res.json()) as { access_token: string };
    auth.set(data.access_token);
  },
  me: () => req<{ username: string; roles: string[] }>("/auth/me"),

  assets: () => req<AssetSummary[]>("/assets"),
  asset: (unit: string) => req<Asset>(`/assets/${encodeURIComponent(unit)}`),
  findings: (unit: string) => req<Finding[]>(`/assets/${encodeURIComponent(unit)}/findings`),
  diagnoses: (unit: string) => req<Finding[]>(`/assets/${encodeURIComponent(unit)}/diagnoses`),
  reports: (unit: string) => req<Report[]>(`/assets/${encodeURIComponent(unit)}/reports`),
  graph: (unit: string) =>
    req<{ unit: string; nodes: GraphNode[]; edges: GraphEdge[] }>(
      `/assets/${encodeURIComponent(unit)}/graph`,
    ),
  runs: (unit: string) => req<EngineRun[]>(`/runs/${encodeURIComponent(unit)}`),

  outlook: (unit: string) => req<Outlook>(`/assets/${encodeURIComponent(unit)}/outlook`),

  feedbackHistory: (identityKey: string) =>
    req<Feedback[]>(`/findings/${encodeURIComponent(identityKey)}/feedback`),
  recordFeedback: (identityKey: string, verdict: Verdict, note = "") =>
    req<Feedback>(`/findings/${encodeURIComponent(identityKey)}/feedback`, {
      method: "POST",
      body: JSON.stringify({ verdict, note }),
    }),
  labelProgress: () => req<LabelProgress>("/feedback/stats"),

  alerts: (limit = 100) => req<Alert[]>(`/alerts?limit=${limit}`),
  unitAlerts: (unit: string, limit = 50) =>
    req<Alert[]>(`/assets/${encodeURIComponent(unit)}/alerts?limit=${limit}`),
  testAlert: () =>
    req<{ sent: boolean; to: string[]; detail: string }>("/alerts/test", { method: "POST" }),

  telemetry: (unit: string, hours = 6) =>
    req<Telemetry>(
      `/assets/${encodeURIComponent(unit)}/telemetry?hours=${hours}&points=90`,
    ),

  analyze: (unit: string) =>
    req<{ unit: string; run_id: string | null; finding_count: number; replayed: boolean }>(
      "/analyze",
      { method: "POST", body: JSON.stringify({ unit }) },
    ),

  ask: (unit: string, question: string, persona: string, history: Turn[] = []) =>
    req<GroundedAnswer & { model?: string }>("/llm/query", {
      method: "POST",
      body: JSON.stringify({ unit, question, persona, history }),
    }),
};
