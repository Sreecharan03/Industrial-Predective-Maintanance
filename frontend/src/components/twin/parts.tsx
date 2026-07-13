/** Machine detail parts.
 *
 *  The difference between a toy and a machine is the small stuff: bevelled edges,
 *  bolt rings, flanged joints, cast ribs, guards, gauges, nameplates. Everything
 *  here is generated — no downloaded assets — but nothing is a bare primitive.
 */
import { RoundedBox } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

/* ── industrial materials ─────────────────────────────────────────── */
export const MAT = {
  paint:   { color: "#3E5563", metalness: 0.45, roughness: 0.42 }, // machine enamel
  paintHi: { color: "#4E6979", metalness: 0.45, roughness: 0.38 },
  steel:   { color: "#C3C8CE", metalness: 0.96, roughness: 0.28 }, // machined steel
  cast:    { color: "#9BA3AB", metalness: 0.85, roughness: 0.52 }, // cast housing
  dark:    { color: "#4A5058", metalness: 0.88, roughness: 0.44 },
  copper:  { color: "#B87333", metalness: 0.95, roughness: 0.26 },
  brass:   { color: "#C9A227", metalness: 0.95, roughness: 0.3 },
  rubber:  { color: "#24282D", metalness: 0.1,  roughness: 0.92 },
  guard:   { color: "#D9A21B", metalness: 0.5,  roughness: 0.55 }, // safety yellow
  glass:   { color: "#DCE6EA", metalness: 0.1,  roughness: 0.08 },
} as const;

type M = keyof typeof MAT;
export const mat = (m: M) => <meshStandardMaterial {...MAT[m]} />;

/* ── bevelled box (machined, not a cube) ──────────────────────────── */
export function Box({
  args, position, rotation, m = "paint", radius = 0.035,
}: {
  args: [number, number, number];
  position?: [number, number, number];
  rotation?: [number, number, number];
  m?: M;
  radius?: number;
}) {
  return (
    <RoundedBox args={args} radius={radius} smoothness={3}
                position={position} rotation={rotation} castShadow receiveShadow>
      {mat(m)}
    </RoundedBox>
  );
}

/* ── ring of bolt heads around a flange ───────────────────────────── */
export function Bolts({
  r, count = 8, size = 0.028, m = "dark",
}: { r: number; count?: number; size?: number; m?: M }) {
  const items = useMemo(
    () => Array.from({ length: count }, (_, i) => (i / count) * Math.PI * 2),
    [count],
  );
  return (
    <group>
      {items.map((a, i) => (
        <mesh key={i} position={[Math.cos(a) * r, 0.026, Math.sin(a) * r]} castShadow>
          <cylinderGeometry args={[size, size, 0.05, 6]} />
          {mat(m)}
        </mesh>
      ))}
    </group>
  );
}

/** Bolted pipe flange. */
export function Flange({ r = 0.24, m = "steel" }: { r?: number; m?: M }) {
  return (
    <group>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[r, r, 0.05, 28]} />
        {mat(m)}
      </mesh>
      <Bolts r={r * 0.72} count={8} />
    </group>
  );
}

/** Cast cooling / stiffening ribs around a housing. */
export function Ribs({
  count = 14, r = 0.52, h = 1.1, m = "cast",
}: { count?: number; r?: number; h?: number; m?: M }) {
  const items = useMemo(
    () => Array.from({ length: count }, (_, i) => (i / count) * Math.PI * 2),
    [count],
  );
  return (
    <group>
      {items.map((a, i) => (
        <mesh key={i}
              position={[Math.cos(a) * r, 0, Math.sin(a) * r]}
              rotation={[0, -a, 0]} castShadow>
          <boxGeometry args={[0.03, h, 0.09]} />
          {mat(m)}
        </mesh>
      ))}
    </group>
  );
}

/** Pressure gauge — dial, bezel, stem. */
export function Gauge({
  position, rotation,
}: { position: [number, number, number]; rotation?: [number, number, number] }) {
  return (
    <group position={position} rotation={rotation}>
      <mesh castShadow>
        <cylinderGeometry args={[0.075, 0.075, 0.05, 20]} />
        {mat("brass")}
      </mesh>
      <mesh position={[0, 0.028, 0]}>
        <cylinderGeometry args={[0.058, 0.058, 0.012, 20]} />
        <meshStandardMaterial color="#F3F1EE" roughness={0.35} metalness={0} />
      </mesh>
      <mesh position={[0, -0.07, 0]}>
        <cylinderGeometry args={[0.022, 0.022, 0.1, 10]} />
        {mat("steel")}
      </mesh>
    </group>
  );
}

/** Electrical terminal / junction box with conduit. */
export function JunctionBox({
  position, rotation,
}: { position: [number, number, number]; rotation?: [number, number, number] }) {
  return (
    <group position={position} rotation={rotation}>
      <Box args={[0.34, 0.26, 0.2]} m="dark" radius={0.02} />
      <mesh position={[0, 0.14, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.045, 0.06, 12]} />
        {mat("steel")}
      </mesh>
      {/* flexible conduit */}
      <mesh position={[0, 0.3, 0]} castShadow>
        <cylinderGeometry args={[0.035, 0.035, 0.34, 10]} />
        {mat("rubber")}
      </mesh>
    </group>
  );
}

/** Hand valve on a line. */
export function Valve({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh castShadow>
        <boxGeometry args={[0.17, 0.17, 0.17]} />
        {mat("cast")}
      </mesh>
      <mesh position={[0, 0.16, 0]} castShadow>
        <cylinderGeometry args={[0.03, 0.03, 0.16, 10]} />
        {mat("steel")}
      </mesh>
      <mesh position={[0, 0.25, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <torusGeometry args={[0.1, 0.022, 8, 20]} />
        {mat("guard")}
      </mesh>
    </group>
  );
}

/** Skid: a real channel frame with feet — not a slab. */
export function Skid({ w = 2.6, d = 1.9 }: { w?: number; d?: number }) {
  const hw = w / 2, hd = d / 2;
  return (
    <group position={[0, -0.95, 0]}>
      {/* long rails */}
      {[-hd + 0.12, hd - 0.12].map((z) => (
        <Box key={z} args={[w, 0.16, 0.14]} position={[0, 0, z]} m="dark" radius={0.02} />
      ))}
      {/* cross members */}
      {[-hw + 0.15, 0, hw - 0.15].map((x) => (
        <Box key={x} args={[0.12, 0.14, d - 0.16]} position={[x, -0.01, 0]} m="dark" radius={0.02} />
      ))}
      {/* anti-vibration feet */}
      {[[-hw + 0.2, -hd + 0.2], [hw - 0.2, -hd + 0.2], [-hw + 0.2, hd - 0.2], [hw - 0.2, hd - 0.2]]
        .map(([x, z], i) => (
          <mesh key={i} position={[x, -0.14, z]} castShadow>
            <cylinderGeometry args={[0.11, 0.13, 0.14, 14]} />
            {mat("rubber")}
          </mesh>
        ))}
    </group>
  );
}

/** Nameplate — the small touch that sells scale. */
export function Nameplate({ position }: { position: [number, number, number] }) {
  return (
    <mesh position={position} castShadow>
      <boxGeometry args={[0.3, 0.16, 0.012]} />
      <meshStandardMaterial color="#D8DCE0" metalness={0.9} roughness={0.25} />
    </mesh>
  );
}

/** Curved pipe elbow (quarter turn). */
export function Elbow({
  position, rotation, r = 0.3, tube = 0.085,
}: {
  position: [number, number, number];
  rotation?: [number, number, number];
  r?: number;
  tube?: number;
}) {
  return (
    <mesh position={position} rotation={rotation} castShadow>
      <torusGeometry args={[r, tube, 12, 20, Math.PI / 2]} />
      {mat("copper")}
    </mesh>
  );
}

/** Fan guard — concentric rings + spokes, like a real cowl. */
export function FanGuard({
  position, rotation, r = 0.5,
}: { position: [number, number, number]; rotation?: [number, number, number]; r?: number }) {
  const rings = [r, r * 0.72, r * 0.44];
  const spokes = useMemo(
    () => Array.from({ length: 6 }, (_, i) => (i / 6) * Math.PI * 2),
    [],
  );
  return (
    <group position={position} rotation={rotation}>
      {rings.map((rr, i) => (
        <mesh key={i} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[rr, 0.014, 8, 32]} />
          {mat("dark")}
        </mesh>
      ))}
      {spokes.map((a, i) => (
        <mesh key={i} rotation={[0, a, Math.PI / 2]}>
          <cylinderGeometry args={[0.012, 0.012, r * 2, 6]} />
          {mat("dark")}
        </mesh>
      ))}
    </group>
  );
}

/** Dished vessel head (torispherical, like a real pressure vessel). */
export function DishedHead({
  position, rotation, r,
}: { position: [number, number, number]; rotation?: [number, number, number]; r: number }) {
  const geo = useMemo(() => new THREE.SphereGeometry(r, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2.4), [r]);
  return (
    <mesh geometry={geo} position={position} rotation={rotation} castShadow receiveShadow>
      {mat("paintHi")}
    </mesh>
  );
}
