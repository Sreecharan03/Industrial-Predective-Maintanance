/** The machines, built from detailed generated geometry.
 *
 *  A screw compressor has a ribbed motor with a terminal box and a fan cowl, a
 *  cast rotor housing with flanged suction and discharge, an oil line and a
 *  sight glass. A pressure vessel has dished heads, a manway, nozzles and
 *  saddles. That detail — plus bevels, bolts and real metal — is what stops it
 *  looking like a balloon.
 */
import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";
import type { ModuleKind } from "./layout";
import {
  Bolts, Box, DishedHead, Elbow, FanGuard, Flange, Gauge, JunctionBox,
  Nameplate, Ribs, Skid, Valve, mat,
} from "./parts";

/* ───────────────────── screw compressor ───────────────────── */
function Compressor() {
  const fan = useRef<Group>(null);
  useFrame((_, d) => { if (fan.current) fan.current.rotation.x += d * 6; });

  return (
    <group>
      <Skid w={2.9} d={1.9} />

      {/* ── motor: ribbed housing, end bells, terminal box, fan cowl ── */}
      <group position={[-0.85, -0.12, 0]} rotation={[0, 0, Math.PI / 2]}>
        <mesh castShadow receiveShadow>
          <cylinderGeometry args={[0.46, 0.46, 1.15, 40]} />
          {mat("paint")}
        </mesh>
        <Ribs count={20} r={0.475} h={1.0} m="paint" />
        {/* end bells */}
        {[-0.62, 0.62].map((y) => (
          <mesh key={y} position={[0, y, 0]} castShadow>
            <cylinderGeometry args={[0.42, 0.46, 0.14, 32]} />
            {mat("cast")}
          </mesh>
        ))}
        {/* shaft */}
        <mesh position={[0, 0.78, 0]} castShadow>
          <cylinderGeometry args={[0.09, 0.09, 0.24, 16]} />
          {mat("steel")}
        </mesh>
        {/* cooling fan behind the cowl */}
        <group ref={fan} position={[0, -0.78, 0]}>
          {Array.from({ length: 7 }, (_, i) => (
            <mesh key={i} rotation={[0, (i / 7) * Math.PI * 2, 0.5]} castShadow>
              <boxGeometry args={[0.3, 0.02, 0.12]} />
              {mat("dark")}
            </mesh>
          ))}
        </group>
      </group>
      <FanGuard position={[-1.55, -0.12, 0]} rotation={[0, 0, Math.PI / 2]} r={0.44} />
      <JunctionBox position={[-0.85, 0.42, 0]} />

      {/* ── rotor housing: cast, tapered, flanged ── */}
      <group position={[0.5, -0.08, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
          <cylinderGeometry args={[0.58, 0.46, 1.5, 36]} />
          {mat("cast")}
        </mesh>
        {/* horizontal split-line bolted joint */}
        <mesh position={[0, 0.02, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.6, 0.48, 0.06, 36]} />
          {mat("dark")}
        </mesh>
        <group position={[0, 0.34, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <Bolts r={0.44} count={10} size={0.024} />
        </group>
        <Nameplate position={[0.1, 0.1, 0.56]} />
      </group>

      {/* ── suction (in, top-left) and discharge (out, right) ── */}
      <group position={[-0.05, 0.62, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.17, 0.17, 0.55, 24]} />
          {mat("copper")}
        </mesh>
        <group position={[0, 0.3, 0]}><Flange r={0.24} /></group>
      </group>

      <group position={[1.28, 0.18, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.14, 0.14, 0.5, 24]} />
          {mat("copper")}
        </mesh>
        <group position={[0.28, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <Flange r={0.2} />
        </group>
      </group>
      <Gauge position={[0.5, 0.55, 0.34]} />
      <Valve position={[1.05, 0.62, 0]} />

      {/* oil return line */}
      <mesh position={[0.4, -0.72, 0.42]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.05, 0.05, 1.5, 12]} />
        {mat("steel")}
      </mesh>
    </group>
  );
}

/* ───────────────────── oil separator ───────────────────── */
function OilVessel() {
  return (
    <group>
      <Skid w={2.0} d={1.7} />
      <group position={[0, 0.05, 0]}>
        <mesh castShadow receiveShadow>
          <cylinderGeometry args={[0.52, 0.52, 1.7, 40]} />
          {mat("paintHi")}
        </mesh>
        <DishedHead position={[0, 0.85, 0]} r={0.52} />
        <DishedHead position={[0, -0.85, 0]} rotation={[Math.PI, 0, 0]} r={0.52} />

        {/* weld seams */}
        {[-0.45, 0.2].map((y) => (
          <mesh key={y} position={[0, y, 0]}>
            <cylinderGeometry args={[0.525, 0.525, 0.02, 40]} />
            {mat("cast")}
          </mesh>
        ))}

        {/* manway + inlet/outlet nozzles */}
        <group position={[0, 1.12, 0]}><Flange r={0.26} m="cast" /></group>
        <mesh position={[0.56, 0.55, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.1, 0.1, 0.3, 16]} />
          {mat("copper")}
        </mesh>
        <mesh position={[-0.56, -0.5, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.09, 0.09, 0.3, 16]} />
          {mat("copper")}
        </mesh>

        {/* oil level sight glass */}
        <mesh position={[0.5, -0.3, 0.24]}>
          <capsuleGeometry args={[0.045, 0.42, 6, 12]} />
          <meshPhysicalMaterial color="#E0A93B" transmission={0.55} thickness={0.4}
                                roughness={0.12} metalness={0} />
        </mesh>
        <Gauge position={[0, 1.3, 0.18]} />
      </group>
    </group>
  );
}

/* ───────────────────── condenser ───────────────────── */
function Condenser() {
  const f1 = useRef<Group>(null);
  const f2 = useRef<Group>(null);
  useFrame((_, d) => {
    if (f1.current) f1.current.rotation.y += d * 4.5;
    if (f2.current) f2.current.rotation.y += d * 4.5;
  });

  return (
    <group>
      <Skid w={2.6} d={2.0} />
      {/* casing */}
      <Box args={[2.2, 1.3, 1.5]} position={[0, -0.1, 0]} m="paint" radius={0.06} />

      {/* tube bundle: coil fins on both faces */}
      {[0.76, -0.76].map((z) =>
        Array.from({ length: 16 }, (_, i) => (
          <mesh key={`${z}-${i}`} position={[-1.0 + i * 0.133, -0.1, z]}>
            <boxGeometry args={[0.045, 1.15, 0.02]} />
            {mat("copper")}
          </mesh>
        )),
      )}
      {/* headers */}
      {[0.78, -0.78].map((z) => (
        <mesh key={z} position={[0, 0.5, z]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.075, 0.075, 2.15, 16]} />
          {mat("steel")}
        </mesh>
      ))}

      {/* twin fans, guarded */}
      {[-0.55, 0.55].map((x, i) => (
        <group key={x} position={[x, 0.6, 0]}>
          <group ref={i === 0 ? f1 : f2}>
            {Array.from({ length: 5 }, (_, b) => (
              <mesh key={b} rotation={[0.4, (b / 5) * Math.PI * 2, 0]} castShadow>
                <boxGeometry args={[0.42, 0.02, 0.16]} />
                {mat("dark")}
              </mesh>
            ))}
          </group>
          <FanGuard position={[0, 0.1, 0]} r={0.42} />
        </group>
      ))}
      <Gauge position={[1.0, 0.2, 0.78]} rotation={[Math.PI / 2, 0, 0]} />
    </group>
  );
}

/* ───────────────────── twin towers (dryer / PSA) ───────────────────── */
function Towers({ tall = false }: { tall?: boolean }) {
  const h = tall ? 2.3 : 1.8;
  const r = 0.38;
  return (
    <group>
      <Skid w={2.2} d={1.7} />
      {[-0.55, 0.55].map((x) => (
        <group key={x} position={[x, tall ? 0.3 : 0.05, 0]}>
          <mesh castShadow receiveShadow>
            <cylinderGeometry args={[r, r, h, 32]} />
            {mat("paintHi")}
          </mesh>
          <DishedHead position={[0, h / 2, 0]} r={r} />
          <DishedHead position={[0, -h / 2, 0]} rotation={[Math.PI, 0, 0]} r={r} />
          {/* support skirt */}
          <mesh position={[0, -h / 2 - 0.22, 0]} castShadow>
            <cylinderGeometry args={[r * 0.9, r * 0.95, 0.3, 20]} />
            {mat("dark")}
          </mesh>
          <group position={[0, h / 2 + 0.16, 0]}><Flange r={0.2} m="cast" /></group>
          <Gauge position={[0, h / 2 + 0.3, 0.16]} />
        </group>
      ))}

      {/* crossover manifold with valves — the giveaway that these are PSA towers */}
      <group position={[0, tall ? 1.62 : 1.12, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.075, 0.075, 1.1, 16]} />
          {mat("copper")}
        </mesh>
        <Valve position={[0, 0.06, 0]} />
      </group>
      <group position={[0, tall ? -0.95 : -0.75, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.065, 0.065, 1.1, 16]} />
          {mat("steel")}
        </mesh>
      </group>
      <Elbow position={[0.55, tall ? 1.62 : 1.12, 0]} rotation={[0, 0, 0]} r={0.22} tube={0.07} />
    </group>
  );
}

/* ───────────────────── air receiver ───────────────────── */
function Receiver() {
  return (
    <group>
      <Skid w={2.7} d={1.8} />
      <group position={[0, 0.12, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
          <cylinderGeometry args={[0.58, 0.58, 1.9, 40]} />
          {mat("paint")}
        </mesh>
        <DishedHead position={[0.95, 0, 0]} rotation={[0, 0, -Math.PI / 2]} r={0.58} />
        <DishedHead position={[-0.95, 0, 0]} rotation={[0, 0, Math.PI / 2]} r={0.58} />

        {/* saddles */}
        {[-0.55, 0.55].map((x) => (
          <group key={x} position={[x, -0.55, 0]}>
            <Box args={[0.22, 0.5, 1.0]} m="dark" radius={0.02} />
          </group>
        ))}
        {/* top nozzle + relief valve + gauge */}
        <mesh position={[-0.35, 0.6, 0]} castShadow>
          <cylinderGeometry args={[0.1, 0.1, 0.24, 16]} />
          {mat("copper")}
        </mesh>
        <Valve position={[0.35, 0.68, 0]} />
        <Gauge position={[-0.35, 0.8, 0]} />
        <Nameplate position={[0, 0.15, 0.59]} />
      </group>
    </group>
  );
}

/* ───────────────────── cooling-water skid ───────────────────── */
function Cooling() {
  const imp = useRef<Group>(null);
  useFrame((_, d) => { if (imp.current) imp.current.rotation.x += d * 5; });
  return (
    <group>
      <Skid w={2.3} d={1.7} />
      {/* shell-and-tube heat exchanger */}
      <group position={[0.25, -0.02, 0]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
          <cylinderGeometry args={[0.42, 0.42, 1.5, 32]} />
          <meshStandardMaterial color="#4E7C86" metalness={0.6} roughness={0.4} />
        </mesh>
        {[-0.78, 0.78].map((x) => (
          <group key={x} position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
            <Flange r={0.44} m="cast" />
          </group>
        ))}
      </group>
      {/* pump + motor */}
      <group position={[-0.85, -0.3, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.3, 0.3, 0.5, 24]} />
          {mat("cast")}
        </mesh>
        <group ref={imp} position={[0, 0, 0.28]}>
          {Array.from({ length: 6 }, (_, i) => (
            <mesh key={i} rotation={[0, 0, (i / 6) * Math.PI * 2]}>
              <boxGeometry args={[0.22, 0.02, 0.05]} />
              {mat("steel")}
            </mesh>
          ))}
        </group>
        <JunctionBox position={[0, 0.42, 0]} />
      </group>
      {/* water lines */}
      <mesh position={[0.25, 0.6, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.1, 0.1, 1.7, 16]} />
        <meshStandardMaterial color="#5FA8B5" metalness={0.85} roughness={0.3} />
      </mesh>
      <Gauge position={[0.25, 0.78, 0.12]} />
    </group>
  );
}

export function MachineModule({ kind }: { kind: ModuleKind }) {
  switch (kind) {
    case "compressor": return <Compressor />;
    case "oil":        return <OilVessel />;
    case "condenser":  return <Condenser />;
    case "dryer":      return <Towers />;
    case "psa":        return <Towers tall />;
    case "receiver":   return <Receiver />;
    case "cooling":    return <Cooling />;
  }
}

/** Flanged pipe run between modules — with elbows, not a bare stick. */
export function Pipe({ from, to }: { from: number; to: number }) {
  const len = to - from;
  if (len <= 0.15) return null;
  return (
    <group>
      <mesh position={[from + len / 2, 0.35, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.085, 0.085, len, 20]} />
        {mat("copper")}
      </mesh>
      {[from + 0.06, to - 0.06].map((x) => (
        <group key={x} position={[x, 0.35, 0]} rotation={[0, 0, Math.PI / 2]}>
          <Flange r={0.13} m="cast" />
        </group>
      ))}
      {/* pipe support stand */}
      <mesh position={[from + len / 2, -0.35, 0]} castShadow>
        <cylinderGeometry args={[0.035, 0.045, 1.35, 10]} />
        {mat("dark")}
      </mesh>
    </group>
  );
}
