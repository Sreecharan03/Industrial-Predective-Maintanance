/** The rotatable machine view.
 *
 *  Geometry comes from the asset's real subsystems; every hotspot is a real
 *  sensor carrying its live reading. Colour = state, always paired with a label.
 *
 *  Realism comes from image-based lighting (built in-memory from Lightformers —
 *  no HDRI download), soft contact shadows, a polished floor, ACES tone mapping
 *  and a bloom pass that makes an alarming sensor genuinely glow.
 */
import {
  ContactShadows, Environment, Html, Lightformer, MeshReflectorMaterial, OrbitControls,
} from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { useRef, useState } from "react";
import { ACESFilmicToneMapping, type Group, type Mesh } from "three";
import type { Asset, SensorTrace, Severity } from "../../lib/api";
import { prettySensor } from "../../lib/ui";
import { buildLayout, hotspotOffsets, type ModuleSpec } from "./layout";
import { MachineModule, Pipe } from "./modules";

const COLOR: Record<Severity, string> = {
  ok: "#15803D",
  info: "#57534E",
  warning: "#B45309",
  critical: "#BE123C",
};

export interface Hot {
  key: string;
  severity: Severity;
  trace?: SensorTrace;
}

function Hotspot({
  hot, position, selected, onSelect,
}: {
  hot: Hot;
  position: [number, number, number];
  selected: boolean;
  onSelect: (k: string) => void;
}) {
  const pin = useRef<Mesh>(null);
  const halo = useRef<Group>(null);
  const [hover, setHover] = useState(false);
  const alert = hot.severity === "critical" || hot.severity === "warning";
  const color = COLOR[hot.severity];

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (pin.current) {
      const pulse = alert ? 1 + Math.sin(t * 3.4) * 0.18 : 1;
      pin.current.scale.setScalar(pulse * (hover || selected ? 1.35 : 1));
    }
    if (halo.current) {
      // an expanding ring on an alarming sensor — motion reads before colour
      const p = (t * 0.7) % 1;
      halo.current.scale.setScalar(1 + p * 2.4);
      const m = halo.current.children[0] as Mesh;
      // @ts-expect-error material opacity
      if (m?.material) m.material.opacity = alert ? (1 - p) * 0.5 : 0;
      halo.current.visible = alert;
    }
  });

  const show = hover || selected || hot.severity === "critical";

  return (
    <group position={position}>
      {/* emissive pin — the bloom pass makes this glow */}
      <mesh
        ref={pin}
        onClick={(e) => { e.stopPropagation(); onSelect(hot.key); }}
        onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = "auto"; }}
      >
        <sphereGeometry args={[0.085, 24, 24]} />
        <meshStandardMaterial
          color={color} emissive={color}
          emissiveIntensity={alert ? 2.6 : 0.7}
          toneMapped={false}
        />
      </mesh>

      <group ref={halo} rotation={[Math.PI / 2, 0, 0]}>
        <mesh>
          <ringGeometry args={[0.1, 0.13, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.5} toneMapped={false} />
        </mesh>
      </group>

      {/* stem to the machine body */}
      <mesh position={[0, -0.3, 0]}>
        <cylinderGeometry args={[0.009, 0.009, 0.6, 8]} />
        <meshBasicMaterial color={color} transparent opacity={0.5} toneMapped={false} />
      </mesh>

      {show && (
        <Html center distanceFactor={9} style={{ pointerEvents: "none" }} zIndexRange={[20, 0]}>
          <div
            className="whitespace-nowrap rounded-lg bg-white/95 px-2 py-1 text-[11px]
                       font-semibold shadow-lg ring-1 ring-black/5 backdrop-blur"
            style={{ color }}
          >
            {prettySensor(hot.key)}
            {hot.trace?.latest && (
              <span className="ml-1 font-bold">
                {hot.trace.latest.value}
                <span className="ml-0.5 font-normal opacity-70">{hot.trace.unit_symbol}</span>
              </span>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}

function Rig({
  modules, positions, hots, selected, onSelect,
}: {
  modules: ModuleSpec[];
  positions: [number, number, number][];
  hots: Record<string, Hot>;
  selected: string | null;
  onSelect: (k: string) => void;
}) {
  return (
    <group position={[0, 0.1, 0]}>
      {positions.slice(0, -1).map((p, i) => (
        <Pipe key={i} from={p[0] + 1.3} to={positions[i + 1][0] - 1.3} />
      ))}

      {modules.map((m, i) => {
        const offsets = hotspotOffsets(m.sensors.length);
        return (
          <group key={m.key} position={positions[i]}>
            <MachineModule kind={m.kind} />

            <Html center position={[0, -1.45, 0]} distanceFactor={12}
                  style={{ pointerEvents: "none" }} zIndexRange={[10, 0]}>
              <div className="whitespace-nowrap rounded-md bg-white/80 px-2 py-0.5 text-[10px]
                              font-bold uppercase tracking-wider text-stone-500 backdrop-blur">
                {m.label}
              </div>
            </Html>

            {m.sensors.map((k, j) =>
              hots[k] ? (
                <Hotspot key={k} hot={hots[k]} position={offsets[j]}
                         selected={selected === k} onSelect={onSelect} />
              ) : null,
            )}
          </group>
        );
      })}
    </group>
  );
}

/** Studio lighting rig — an HDRI assembled in-memory, so metal has something to
 *  reflect without downloading anything. */
function Studio() {
  return (
    <Environment resolution={256} frames={1}>
      <group rotation={[-Math.PI / 3, 0, 0]}>
        <Lightformer intensity={4} rotation-x={Math.PI / 2} position={[0, 6, -9]} scale={[12, 12, 1]} />
        <Lightformer intensity={2} rotation-y={Math.PI / 2} position={[-7, 2, 0]} scale={[10, 6, 1]} />
        <Lightformer intensity={2.4} rotation-y={-Math.PI / 2} position={[7, 2, 0]} scale={[10, 6, 1]} />
        <Lightformer form="ring" color="#C9B8FF" intensity={2.2}
                     position={[-4, 4, -3]} scale={3} />
      </group>
    </Environment>
  );
}

export default function Twin({
  asset, hots, selected, onSelect,
}: {
  asset: Asset;
  hots: Record<string, Hot>;
  selected: string | null;
  onSelect: (k: string) => void;
}) {
  const { modules, positions } = buildLayout(asset.subsystems);
  const span = Math.max(modules.length, 3);

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      gl={{ antialias: true, toneMapping: ACESFilmicToneMapping, toneMappingExposure: 1.05 }}
      camera={{ position: [span * 1.4, 3.6, span * 2.5], fov: 34 }}
      onPointerMissed={() => onSelect("")}
    >
      <color attach="background" args={["#F4F2F0"]} />
      <fog attach="fog" args={["#F4F2F0", 22, 52]} />

      <Studio />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[7, 11, 6]} intensity={2.1} castShadow
        shadow-mapSize={[2048, 2048]} shadow-bias={-0.0005}
      />
      <directionalLight position={[-9, 5, -7]} intensity={0.5} color="#BFA9FF" />

      <Rig modules={modules} positions={positions} hots={hots}
           selected={selected} onSelect={onSelect} />

      {/* polished plant floor — reflections sell the metal */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.28, 0]} receiveShadow>
        <planeGeometry args={[120, 120]} />
        <MeshReflectorMaterial
          resolution={512} mixBlur={1.1} mixStrength={12} blur={[380, 90]}
          depthScale={1.1} minDepthThreshold={0.5} maxDepthThreshold={1.2}
          color="#E9E5E1" metalness={0.35} roughness={0.85} mirror={0}
        />
      </mesh>

      <ContactShadows position={[0, -1.26, 0]} opacity={0.5} scale={span * 7}
                      blur={2.2} far={5} />

      <OrbitControls
        makeDefault enablePan={false} enableDamping dampingFactor={0.06}
        minPolarAngle={0.15} maxPolarAngle={Math.PI / 2.12}
        minDistance={4.5} maxDistance={span * 5.5}
        autoRotate autoRotateSpeed={0.35}
        target={[0, 0.1, 0]}
      />

      <EffectComposer multisampling={4}>
        <Bloom intensity={0.85} luminanceThreshold={1.0} luminanceSmoothing={0.3} mipmapBlur />
        <Vignette eskil={false} offset={0.22} darkness={0.55} />
      </EffectComposer>
    </Canvas>
  );
}
