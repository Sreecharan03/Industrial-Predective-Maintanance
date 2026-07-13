/** Sensor trend (ADR-018 §2: telemetry is presentation data, never reasoning input).
 *
 *  One series, so no legend — the title names it. Thin 2px line, recessive axes,
 *  the operating band drawn as a quiet reference area, and a crosshair tooltip.
 *  A breaching sensor is marked with an icon + label, never colour alone.
 */
import {
  Area,
  AreaChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SensorTrace } from "../lib/api";

const BRAND = "#7C3AED";
const CRIT = "#BE123C";

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Is the latest reading outside its supplied operating band? */
export function isBreaching(s: SensorTrace): boolean {
  if (!s.threshold || !s.latest) return false;
  const { low, high } = s.threshold;
  return (
    (low != null && s.latest.value < low) || (high != null && s.latest.value > high)
  );
}

export function SensorChart({ sensor, hours }: { sensor: SensorTrace; hours: number }) {
  const breach = isBreaching(sensor);
  const stroke = breach ? CRIT : BRAND;
  const data = sensor.points.map((p) => ({ ...p, label: fmtTime(p.t) }));

  if (!data.length) {
    return (
      <div className="flex h-24 items-center justify-center text-xs text-ink-3">
        No readings in the last {hours}h
      </div>
    );
  }

  const values = data.map((d) => d.v);
  const lo = sensor.threshold?.low ?? null;
  const hi = sensor.threshold?.high ?? null;
  // Keep the band in view when it exists, but never let it flatten the signal.
  const min = Math.min(...values, lo ?? Infinity);
  const max = Math.max(...values, hi ?? -Infinity);
  const pad = (max - min || 1) * 0.12;

  return (
    <div className="h-28">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`g-${sensor.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.16} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>

          {lo != null && hi != null && (
            <ReferenceArea y1={lo} y2={hi} fill="#0F9D8F" fillOpacity={0.06} />
          )}
          {hi != null && (
            <ReferenceLine y={hi} stroke="#0F9D8F" strokeDasharray="3 3" strokeOpacity={0.45} />
          )}
          {lo != null && (
            <ReferenceLine y={lo} stroke="#0F9D8F" strokeDasharray="3 3" strokeOpacity={0.45} />
          )}

          <XAxis dataKey="label" hide />
          <YAxis domain={[min - pad, max + pad]} hide />
          <Tooltip
            cursor={{ stroke: "#A8A29E", strokeWidth: 1 }}
            contentStyle={{
              borderRadius: 12,
              border: "1px solid #E7E5E4",
              boxShadow: "0 8px 24px rgba(28,25,23,.08)",
              fontSize: 12,
              padding: "8px 10px",
            }}
            labelStyle={{ color: "#78716C", marginBottom: 2 }}
            formatter={(v: number) => [`${v} ${sensor.unit_symbol}`, sensor.display_name]}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={2}
            fill={`url(#g-${sensor.key})`}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 2, stroke: "#fff" }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
