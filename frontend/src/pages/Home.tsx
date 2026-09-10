import React, { useEffect, useState, Suspense, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { HealthResponse } from "../types";

import { Canvas, useFrame } from "@react-three/fiber";
import {
  Float,
  Environment,
  MeshTransmissionMaterial,
  OrbitControls,
  MeshDistortMaterial,
  Sphere,
  ContactShadows,
  PerspectiveCamera,
} from "@react-three/drei";
import { EffectComposer, Bloom, ChromaticAberration, Vignette, Noise } from "@react-three/postprocessing";
import { BlendFunction } from "postprocessing";
import * as THREE from "three";

/* ================= PARTICLES ================= */

function Particles({ count = 400 }: { count?: number }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      t: Math.random() * 100,
      factor: 20 + Math.random() * 40,
      speed: 0.01 + Math.random() / 100,
      xFactor: -10 + Math.random() * 20,
      yFactor: -10 + Math.random() * 20,
      zFactor: -10 + Math.random() * 20,
    }));
  }, [count]);

  useFrame(() => {
    if (!mesh.current) return;

    particles.forEach((p, i) => {
      p.t += p.speed;
      const s = Math.cos(p.t);

      dummy.position.set(
        p.xFactor + Math.cos(p.t) * 2,
        p.yFactor + Math.sin(p.t) * 2,
        p.zFactor + Math.sin(p.t) * 2
      );
      dummy.scale.setScalar(Math.abs(s) * 0.5);
      dummy.updateMatrix();
      mesh.current!.setMatrixAt(i, dummy.matrix);
    });

    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined as any, undefined as any, count]}>
      <dodecahedronGeometry args={[0.15]} />
      <meshStandardMaterial
        color="#ff1744"
        emissive="#ff1744"
        emissiveIntensity={2}
        toneMapped={false}
      />
    </instancedMesh>
  );
}

/* ================= GLASS SPHERE ================= */

function GlassSphere() {
  const ref = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.getElapsedTime();
    ref.current.rotation.y = t * 0.3;
    ref.current.rotation.z = Math.sin(t * 0.2) * 0.2;
  });

  return (
    <Float speed={2} rotationIntensity={1} floatIntensity={2}>
      <mesh ref={ref} scale={3}>
        <sphereGeometry args={[1, 128, 128]} />
        <MeshTransmissionMaterial
          transmission={1}
          roughness={0.1}
          thickness={1.5}
          ior={1.5}
          chromaticAberration={0.3}
          distortion={0.2}
          distortionScale={0.4}
          temporalDistortion={0.1}
          color="#ff1744"
        />
      </mesh>
    </Float>
  );
}

/* ================= SCENE ================= */

function Scene() {
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 0, 12]} />
      <OrbitControls enablePan={false} autoRotate autoRotateSpeed={1.5} />
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={2} color="#ff1744" />

      {/* Background distortion sphere */}
      <Sphere args={[30, 64, 64]} scale={[-1, 1, 1]}>
        <MeshDistortMaterial color="#0a0a1a" distort={0.2} speed={1.5} />
      </Sphere>

      <GlassSphere />
      <Particles />

      {/* Environment */}
      <Environment preset="city" />
      <ContactShadows position={[0, -5, 0]} opacity={0.4} scale={40} blur={2} />

      {/* Postprocessing */}
      <EffectComposer>
        <Bloom intensity={2} luminanceThreshold={0.2} mipmapBlur />
        <ChromaticAberration blendFunction={BlendFunction.NORMAL} offset={[0.0015, 0.0015]} />
        <Vignette />
        <Noise opacity={0.02} />
      </EffectComposer>
    </>
  );
}

/* ================= MAIN HOME COMPONENT ================= */

export default function Home() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);

  return (
    <div className="relative w-full h-screen overflow-hidden bg-black">
      {/* 3D Hero Scene */}
      <Canvas shadows dpr={[1, 2]} gl={{ antialias: true }}>
        <Suspense fallback={null}>
          <Scene />
        </Suspense>
      </Canvas>

      {/* Overlay UI */}
      <div className="absolute inset-0 z-10 flex flex-col items-center justify-center pointer-events-none">
        <h1
          className="text-[6vw] md:text-[5vw] font-black leading-none text-white"
          style={{ textShadow: "0 0 20px #ff1744" }}
        >
          LifeLine Core
        </h1>

        <p
          className="mt-4 text-[2vw] md:text-[1.4vw] text-white tracking-[0.1em]"
          style={{ textShadow: "0 0 10px #ff1744" }}
        >
          Seconds Save Lives
        </p>

        <button
          onClick={() => navigate("/dashboard")}
          className="pointer-events-auto mt-10 px-10 py-4 text-lg font-bold text-white bg-accent rounded-full cursor-pointer transition-all hover:scale-105 active:scale-95"
          style={{ boxShadow: "0 0 20px rgba(59,130,246,0.5)" }}
        >
          GET STARTED
        </button>

        {/* System health panel */}
        {health && (
          <div className="pointer-events-none mt-6 glass rounded-xl px-5 py-2">
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                Online
              </span>
              <span className="text-slate-700">|</span>
              <span>{health.llm_provider.toUpperCase()}</span>
              <span className="text-slate-700">|</span>
              <span>{health.model}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
