/** Digital-twin layout.
 *
 *  The rig is built from the machine's REAL subsystems (the platform already
 *  groups every sensor into one), laid out along the process flow. Nothing is
 *  invented: if an asset has no condenser, no condenser is drawn.
 *
 *  This is a schematic representation of the equipment — not a CAD model of the
 *  physical unit — so it stays honest about what it is.
 */

export type ModuleKind =
  | "compressor"
  | "oil"
  | "condenser"
  | "dryer"
  | "receiver"
  | "cooling"
  | "psa";

export interface ModuleSpec {
  key: string;          // subsystem key
  kind: ModuleKind;
  label: string;
  sensors: string[];
}

/** Which 3D module represents each subsystem, and where it sits in the flow. */
const KIND: Record<string, { kind: ModuleKind; order: number; label: string }> = {
  compression:         { kind: "compressor", order: 0, label: "Compressor" },
  cooling_water:       { kind: "cooling",    order: 1, label: "Cooling water" },
  oil_system:          { kind: "oil",        order: 2, label: "Oil system" },
  condenser:           { kind: "condenser",  order: 3, label: "Condenser" },
  air_dryer:           { kind: "dryer",      order: 4, label: "Air dryer" },
  air_supply:          { kind: "receiver",   order: 5, label: "Air receiver" },
  nitrogen_generation: { kind: "psa",        order: 6, label: "N₂ generation" },
};

export const SPACING = 3.4;

/** Build the rig from whatever subsystems this asset actually has. */
export function buildLayout(
  subsystems: { key: string; display_name: string; sensor_keys: string[] }[],
): { modules: ModuleSpec[]; positions: [number, number, number][] } {
  const modules = subsystems
    .filter((s) => KIND[s.key])
    .sort((a, b) => KIND[a.key].order - KIND[b.key].order)
    .map<ModuleSpec>((s) => ({
      key: s.key,
      kind: KIND[s.key].kind,
      label: KIND[s.key].label ?? s.display_name,
      sensors: s.sensor_keys,
    }));

  // Centre the rig on the origin so the camera framing works for 3 or 7 modules.
  const span = (modules.length - 1) * SPACING;
  const positions = modules.map<[number, number, number]>((_, i) => [
    i * SPACING - span / 2,
    0,
    0,
  ]);
  return { modules, positions };
}

/** Sensor hotspots ring the module they belong to, so many sensors stay readable. */
export function hotspotOffsets(count: number): [number, number, number][] {
  if (count === 1) return [[0, 1.5, 0]];
  return Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2 - Math.PI / 2;
    const r = 1.15;
    // lift alternate pins so dense clusters don't overlap
    const y = 1.15 + (i % 2 === 0 ? 0.42 : 0);
    return [Math.cos(a) * r, y, Math.sin(a) * r];
  });
}
