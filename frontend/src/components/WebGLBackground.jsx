/**
 * WebGLBackground – full-page, persistent Three.js scene (React Three Fiber)
 * that sits fixed behind all landing-page content. Unlike a boxed static
 * viewer, this is genuinely alive: it auto-rotates, tilts toward the
 * cursor, and dollies/rotates as the page scrolls — driven by two plain
 * `window` listeners feeding refs that a single `useFrame` loop reads and
 * damps each frame (no React re-renders in the hot path).
 *
 * The centerpiece is a real backbone trace of COX-2 (PDB 1CX2, chain A —
 * one of DrugForge's own ADMET targets) parsed from a static asset,
 * rendered as a glowing gradient tube with a companion helical strand
 * (DNA-style) and an ambient GPU particle field around it.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useDrugForge } from '../context/DrugForgeContext.jsx';
import { isPerformanceMode } from '../utils/performanceMode';

const PDB_URL = '/protein/1cx2-hero.pdb';

// Palette (mirrors tailwind.config.js `clay`/`bio` tokens)
const COLOR_A = new THREE.Color('#8B5CF6'); // bio.violet
const COLOR_B = new THREE.Color('#2DD4BF'); // bio.teal
const COLOR_C = new THREE.Color('#8E7767'); // clay.DEFAULT
const HELIX_COLOR = new THREE.Color('#8B5CF6');

/* -- pointer + scroll tracking (plain refs, no re-renders) --------------- */
function usePointerScroll() {
  const pointer = useRef({ x: 0, y: 0 });
  const scroll = useRef(0);

  useEffect(() => {
    const onMove = (e) => {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      scroll.current = max > 0 ? Math.min(Math.max(window.scrollY / max, 0), 1) : 0;
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('scroll', onScroll);
    };
  }, []);

  return { pointer, scroll };
}

/* -- some environments' ResizeObserver never fires its initial callback
 *    on observe(), leaving the R3F canvas stuck at the browser-default
 *    300x150 buffer. A defensive `resize` dispatch shortly after mount
 *    forces R3F to remeasure — a no-op where ResizeObserver behaves
 *    correctly, a fix where it doesn't. -------------------------------- */
function useForceInitialResize() {
  useEffect(() => {
    const id = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    return () => cancelAnimationFrame(id);
  }, []);
}

/* -- parse CA backbone trace from a .pdb text blob ------------------------ */
function parseBackbone(pdbText) {
  const points = [];
  const lines = pdbText.split('\n');
  for (const line of lines) {
    if (line.slice(0, 4) !== 'ATOM') continue;
    if (line.slice(12, 16).trim() !== 'CA') continue;
    const x = parseFloat(line.slice(30, 38));
    const y = parseFloat(line.slice(38, 46));
    const z = parseFloat(line.slice(46, 54));
    if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
      points.push(new THREE.Vector3(x, y, z));
    }
  }
  // Center + normalize scale so the structure is a consistent on-screen size.
  const box = new THREE.Box3().setFromPoints(points);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length() || 1;
  const scale = 7 / size;
  return points.map((p) => p.clone().sub(center).multiplyScalar(scale));
}

/* -- gradient tube material (custom lit shader, palette-driven) ---------- */
function useGradientMaterial(colorA, colorB, colorC) {
  return useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: {
          colorA: { value: colorA },
          colorB: { value: colorB },
          colorC: { value: colorC },
        },
        vertexShader: `
          varying vec2 vUv;
          varying vec3 vNormalW;
          void main() {
            vUv = uv;
            vNormalW = normalize(mat3(modelMatrix) * normal);
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: `
          varying vec2 vUv;
          varying vec3 vNormalW;
          uniform vec3 colorA;
          uniform vec3 colorB;
          uniform vec3 colorC;
          void main() {
            float t = vUv.x;
            vec3 base = t < 0.5 ? mix(colorA, colorB, t * 2.0) : mix(colorB, colorC, (t - 0.5) * 2.0);
            float light = clamp(dot(normalize(vNormalW), normalize(vec3(0.4, 0.7, 0.6))), 0.25, 1.0);
            gl_FragColor = vec4(base * light, 1.0);
          }
        `,
      }),
    [colorA, colorB, colorC]
  );
}

/* -- the animated molecule group ------------------------------------------ */
function MoleculeStructure({ pointer, scroll, reduced }) {
  const groupRef = useRef();
  const [points, setPoints] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(PDB_URL)
      .then((res) => res.text())
      .then((text) => {
        if (!cancelled) setPoints(parseBackbone(text));
      })
      .catch((err) => console.error('[WebGLBackground] failed to load structure:', err));
    return () => { cancelled = true; };
  }, []);

  const curve = useMemo(
    () => (points ? new THREE.CatmullRomCurve3(points, false, 'catmullrom', 0.4) : null),
    [points]
  );

  const tubeGeometry = useMemo(
    () => (curve ? new THREE.TubeGeometry(curve, 300, 0.09, 8, false) : null),
    [curve]
  );

  const helixGeometry = useMemo(() => {
    if (!curve) return null;
    const n = 300;
    const helixPoints = [];
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const base = curve.getPointAt(t);
      const tangent = curve.getTangentAt(t);
      const normal = new THREE.Vector3(0, 1, 0).cross(tangent).normalize();
      if (normal.lengthSq() < 0.001) normal.set(1, 0, 0);
      const offset = normal.multiplyScalar(0.55 * Math.sin(t * Math.PI * 24));
      helixPoints.push(base.clone().add(offset));
    }
    const helixCurve = new THREE.CatmullRomCurve3(helixPoints);
    return new THREE.TubeGeometry(helixCurve, 300, 0.035, 6, false);
  }, [curve]);

  const tubeMaterial = useGradientMaterial(COLOR_A, COLOR_B, COLOR_C);
  const helixMaterial = useMemo(
    () => new THREE.MeshBasicMaterial({ color: HELIX_COLOR, transparent: true, opacity: 0.55 }),
    []
  );

  // Dispose imperative GPU resources on unmount / regeneration.
  useEffect(() => () => tubeGeometry?.dispose(), [tubeGeometry]);
  useEffect(() => () => helixGeometry?.dispose(), [helixGeometry]);
  useEffect(() => () => tubeMaterial.dispose(), [tubeMaterial]);
  useEffect(() => () => helixMaterial.dispose(), [helixMaterial]);

  useFrame((state, delta) => {
    if (!groupRef.current) return;
    const dt = Math.min(delta, 1 / 30);

    if (!reduced) {
      groupRef.current.rotation.y += dt * 0.18;
    }

    // Cursor tilt — damped toward pointer position.
    const targetTiltX = pointer.current.y * 0.35;
    const targetTiltZ = -pointer.current.x * 0.35;
    groupRef.current.rotation.x += (targetTiltX - groupRef.current.rotation.x) * (1 - Math.exp(-4 * dt));
    groupRef.current.rotation.z += (targetTiltZ - groupRef.current.rotation.z) * (1 - Math.exp(-4 * dt));

    // Scroll — extra spin, drift toward center, and gentle vertical motion.
    const s = scroll.current;
    groupRef.current.rotation.y += s * 0.002;
    groupRef.current.position.y = -s * 2.2;
    groupRef.current.position.x = 2.3 * (1 - s);
    groupRef.current.scale.setScalar(1 - s * 0.15);
  });

  if (!tubeGeometry || !helixGeometry) return null;

  return (
    <group ref={groupRef}>
      <mesh geometry={tubeGeometry} material={tubeMaterial} />
      <mesh geometry={helixGeometry} material={helixMaterial} />
    </group>
  );
}

/* -- ambient GPU particle field ------------------------------------------- */
function ParticleField({ pointer, count }) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 24;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 16;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 14 - 4;
      seeds[i] = Math.random() * Math.PI * 2;
    }
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('seed', new THREE.BufferAttribute(seeds, 1));
    return geo;
  }, [count]);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: {
          u_time: { value: 0 },
          u_color: { value: new THREE.Color('#8B5CF6') },
          u_parallax: { value: new THREE.Vector2(0, 0) },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: `
          attribute float seed;
          uniform float u_time;
          uniform vec2 u_parallax;
          void main() {
            vec3 p = position;
            p.x += sin(u_time * 0.15 + seed) * 0.4 + u_parallax.x;
            p.y += cos(u_time * 0.12 + seed) * 0.3 + u_parallax.y;
            vec4 mv = modelViewMatrix * vec4(p, 1.0);
            gl_PointSize = (1.6 + 1.4 * sin(seed)) * (60.0 / -mv.z);
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: `
          uniform vec3 u_color;
          void main() {
            float d = length(gl_PointCoord - 0.5);
            if (d > 0.5) discard;
            float alpha = smoothstep(0.5, 0.0, d) * 0.5;
            gl_FragColor = vec4(u_color, alpha);
          }
        `,
      }),
    []
  );

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  useFrame((state) => {
    material.uniforms.u_time.value = state.clock.elapsedTime;
    material.uniforms.u_parallax.value.set(pointer.current.x * -0.6, pointer.current.y * 0.4);
  });

  return <points geometry={geometry} material={material} />;
}

/* -- camera rig: scroll-driven dolly -------------------------------------- */
function CameraRig({ scroll }) {
  const { camera } = useThree();

  useFrame((state, delta) => {
    const dt = Math.min(delta, 1 / 30);
    const s = scroll.current;
    const targetZ = 9 - s * 3;
    camera.position.z += (targetZ - camera.position.z) * (1 - Math.exp(-3 * dt));
    camera.lookAt(0, 0, 0);
  });

  return null;
}

const WebGLBackground = ({ className = '' }) => {
  const { isDarkMode } = useDrugForge();
  const { pointer, scroll } = usePointerScroll();
  const reduced = useRef(isPerformanceMode()).current;
  const particleCount = reduced ? 500 : 1600;
  useForceInitialResize();

  return (
    <div className={className} aria-hidden="true">
      <Canvas
        dpr={[1, 2]}
        frameloop="always"
        gl={{ antialias: false, alpha: true, powerPreference: 'default', preserveDrawingBuffer: true }}
        camera={{ position: [0, 0, 9], fov: 45 }}
      >
        <ambientLight intensity={isDarkMode ? 0.5 : 0.8} />
        <directionalLight position={[4, 6, 5]} intensity={isDarkMode ? 1.1 : 1.4} />
        <MoleculeStructure pointer={pointer} scroll={scroll} reduced={reduced} />
        <ParticleField pointer={pointer} count={particleCount} />
        <CameraRig scroll={scroll} />
      </Canvas>
    </div>
  );
};

export default WebGLBackground;
