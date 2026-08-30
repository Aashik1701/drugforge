/**
 * DiscoveryField — the hero WebGL scene, redesigned to communicate the
 * product concept rather than decorate it. Semantic mapping:
 *
 *   points        = candidate molecules drifting in chemical space
 *   small spheres = a candidate in flight toward a decision
 *   center glow   = the cheap-evidence decision point
 *   most flights  = fade out (exploit / confident, no further compute)
 *   some flights  = continue to the target cluster (investigate / uncertain)
 *   target cluster= a real, downsampled COX-2 backbone (public structural
 *                   data already in this repo) — a stand-in for "run the
 *                   physics-based experiment"
 *   arrival pulse = observed evidence coming back
 *   thin lines    = evidence relationships between a few candidates and the
 *                   decision point
 *
 * Performance contract (all required, see plan):
 *  - one Canvas, dpr=1, antialias off, unlit materials only (no lights).
 *  - low, fixed point/flight counts (lower again on narrow viewports).
 *  - paused (frameloop="never") when the hero scrolls out of view
 *    (IntersectionObserver) or the tab is hidden (visibilitychange).
 *  - prefers-reduced-motion renders exactly one static frame
 *    (frameloop="demand") and skips the flight timers entirely.
 *  - a plain error boundary renders a static SVG fallback if WebGL context
 *    creation throws, so there is always a real fallback visual.
 */

import React, { Component, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import cox2Points from './cox2-backbone.json';

const CANDIDATE_COLOR = new THREE.Color('#8B5CF6'); // violet
const TARGET_COLOR = new THREE.Color('#2DD4BF'); // teal
const DECISION_COLOR = new THREE.Color('#8B5CF6');

const FLIGHT_SLOTS = 3;
const FLIGHT_DURATION = 1.6; // seconds per leg
const INVESTIGATE_PROBABILITY = 0.35;

/* -- environment hooks --------------------------------------------------- */
function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (e) => setReduced(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return reduced;
}

function useActive(containerRef) {
  const [inView, setInView] = useState(true);
  const [tabVisible, setTabVisible] = useState(() => typeof document === 'undefined' || !document.hidden);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.1 });
    io.observe(el);
    return () => io.disconnect();
  }, [containerRef]);

  useEffect(() => {
    const onVis = () => setTabVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  return inView && tabVisible;
}

/* -- error boundary -> static fallback ------------------------------------ */
class CanvasBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err) {
    console.error('[DiscoveryField] WebGL scene failed, showing static fallback:', err);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/* -- static SVG fallback (WebGL unavailable, or an error was thrown) ----- */
const StaticFallback = () => (
  <svg viewBox="0 0 400 300" className="w-full h-full opacity-70" aria-hidden="true">
    <g stroke="#8B5CF6" strokeWidth="0.6" opacity="0.5">
      <line x1="60" y1="60" x2="200" y2="150" />
      <line x1="340" y1="50" x2="200" y2="150" />
      <line x1="80" y1="230" x2="200" y2="150" />
    </g>
    <circle cx="200" cy="150" r="10" fill="#8B5CF6" />
    <circle cx="60" cy="60" r="5" fill="#8B5CF6" opacity="0.7" />
    <circle cx="340" cy="50" r="5" fill="#8B5CF6" opacity="0.7" />
    <circle cx="80" cy="230" r="5" fill="#8B5CF6" opacity="0.7" />
    {cox2Points.slice(0, 60).map(([x, y], i) => (
      <circle key={i} cx={300 + x * 8} cy={150 + y * 8} r="1.1" fill="#2DD4BF" opacity="0.6" />
    ))}
  </svg>
);

/* -- candidate field: static drifting points ------------------------------ */
function CandidateField({ count }) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const r = 3.5 + Math.random() * 2.5;
      const theta = Math.random() * Math.PI * 2;
      const y = (Math.random() - 0.5) * 4;
      positions[i * 3] = Math.cos(theta) * r;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = Math.sin(theta) * r - 1.5;
      seeds[i] = Math.random() * Math.PI * 2;
    }
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('seed', new THREE.BufferAttribute(seeds, 1));
    return geo;
  }, [count]);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: { u_time: { value: 0 }, u_color: { value: CANDIDATE_COLOR } },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: `
          attribute float seed;
          uniform float u_time;
          void main() {
            vec3 p = position;
            p.x += sin(u_time * 0.1 + seed) * 0.25;
            p.y += cos(u_time * 0.08 + seed) * 0.2;
            vec4 mv = modelViewMatrix * vec4(p, 1.0);
            gl_PointSize = 2.5 * (50.0 / -mv.z);
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: `
          uniform vec3 u_color;
          void main() {
            float d = length(gl_PointCoord - 0.5);
            if (d > 0.5) discard;
            gl_FragColor = vec4(u_color, smoothstep(0.5, 0.0, d) * 0.7);
          }
        `,
      }),
    []
  );

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  useFrame((state) => {
    material.uniforms.u_time.value = state.clock.elapsedTime;
  });

  return <points geometry={geometry} material={material} />;
}

/* -- target cluster: the real, downsampled COX-2 backbone ---------------- */
function TargetCluster({ pulseRef }) {
  const groupRef = useRef();
  const materialRef = useRef();

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(cox2Points.length * 3);
    cox2Points.forEach(([x, y, z], i) => {
      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
    });
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return geo;
  }, []);

  const material = useMemo(
    () =>
      new THREE.PointsMaterial({
        color: TARGET_COLOR,
        size: 0.045,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
      }),
    []
  );

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  useFrame((state, delta) => {
    const dt = Math.min(delta, 1 / 30);
    if (groupRef.current) groupRef.current.rotation.y += dt * 0.06;
    // Decay any arrival pulse smoothly back to baseline opacity.
    const target = pulseRef.current > 0 ? 1 : 0.55;
    material.opacity += (target - material.opacity) * (1 - Math.exp(-4 * dt));
    if (pulseRef.current > 0) pulseRef.current -= dt;
  });

  return (
    <group ref={groupRef} position={[3.6, 0.4, -1]}>
      <points geometry={geometry} material={material} ref={materialRef} />
    </group>
  );
}

/* -- decision point: subtle pulsing glow at the origin -------------------- */
function DecisionPoint() {
  const ref = useRef();
  const geometry = useMemo(() => new THREE.IcosahedronGeometry(0.16, 1), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ color: DECISION_COLOR, transparent: true, opacity: 0.85 }), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);
  useFrame((state) => {
    if (!ref.current) return;
    const s = 1 + Math.sin(state.clock.elapsedTime * 1.4) * 0.12;
    ref.current.scale.setScalar(s);
  });
  return <mesh ref={ref} geometry={geometry} material={material} />;
}

/* -- flights: a small, fixed pool of candidates traveling to a decision --- */
function Flights({ reduced, pulseRef }) {
  const flightRefs = useRef(
    Array.from({ length: FLIGHT_SLOTS }, () => ({
      mesh: null,
      active: false,
      leg: 0, // 0 = field -> decision, 1 = decision -> target (investigate)
      progress: 0,
      curve: new THREE.QuadraticBezierCurve3(new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()),
      investigate: false,
    }))
  );

  const spawnTimer = useRef(0);
  const geometry = useMemo(() => new THREE.IcosahedronGeometry(0.05, 0), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ color: CANDIDATE_COLOR, transparent: true }), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  const randomFieldPoint = () => {
    const r = 3.5 + Math.random() * 2.5;
    const theta = Math.random() * Math.PI * 2;
    return new THREE.Vector3(Math.cos(theta) * r, (Math.random() - 0.5) * 4, Math.sin(theta) * r - 1.5);
  };

  useFrame((state, delta) => {
    if (reduced) return;
    const dt = Math.min(delta, 1 / 30);
    const flights = flightRefs.current;

    spawnTimer.current -= dt;
    if (spawnTimer.current <= 0) {
      spawnTimer.current = 1.1 + Math.random() * 1.1;
      const idle = flights.find((f) => !f.active);
      if (idle) {
        idle.active = true;
        idle.leg = 0;
        idle.progress = 0;
        const from = randomFieldPoint();
        const to = new THREE.Vector3(0, 0, 0);
        const control = from.clone().lerp(to, 0.5).add(new THREE.Vector3(0, 1, 0));
        idle.curve.v0.copy(from);
        idle.curve.v1.copy(control);
        idle.curve.v2.copy(to);
        idle.investigate = Math.random() < INVESTIGATE_PROBABILITY;
      }
    }

    const scratch = new THREE.Vector3();
    flights.forEach((f) => {
      if (!f.active || !f.mesh) return;
      f.progress += dt / FLIGHT_DURATION;
      const t = Math.min(f.progress, 1);
      f.curve.getPoint(t, scratch);
      f.mesh.position.copy(scratch);
      f.mesh.material.opacity = f.leg === 0 ? 1 - t * 0.1 : 1 - t * 0.7;

      if (f.progress >= 1) {
        if (f.leg === 0 && f.investigate) {
          f.leg = 1;
          f.progress = 0;
          const from = f.curve.v2.clone();
          const to = new THREE.Vector3(3.6, 0.4, -1);
          const control = from.clone().lerp(to, 0.5).add(new THREE.Vector3(0, 0.8, 0));
          f.curve.v0.copy(from);
          f.curve.v1.copy(control);
          f.curve.v2.copy(to);
        } else {
          if (f.leg === 1) pulseRef.current = 0.6; // arrival = observed evidence
          f.active = false;
          f.mesh.position.set(9999, 9999, 9999);
        }
      }
    });
  });

  return (
    <>
      {flightRefs.current.map((_, i) => (
        <mesh
          key={i}
          geometry={geometry}
          material={material.clone()}
          ref={(m) => {
            if (m) flightRefs.current[i].mesh = m;
          }}
          position={[9999, 9999, 9999]}
        />
      ))}
    </>
  );
}

/* -- evidence lines: a few static links from field points to the decision - */
function EvidenceLines() {
  const geometry = useMemo(() => {
    const points = [];
    const anchors = [
      new THREE.Vector3(2.6, 1.2, -1.5),
      new THREE.Vector3(-2.8, -0.8, -2),
      new THREE.Vector3(0.6, -1.6, -3),
    ];
    anchors.forEach((a) => {
      points.push(a, new THREE.Vector3(0, 0, 0));
    });
    return new THREE.BufferGeometry().setFromPoints(points);
  }, []);
  const material = useMemo(
    () => new THREE.LineBasicMaterial({ color: CANDIDATE_COLOR, transparent: true, opacity: 0.18 }),
    []
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);
  return <lineSegments geometry={geometry} material={material} />;
}

/* -- scene root ------------------------------------------------------------ */
function Scene({ count, reduced }) {
  const pulseRef = useRef(0);
  return (
    <>
      <CandidateField count={count} />
      <EvidenceLines />
      <DecisionPoint />
      <TargetCluster pulseRef={pulseRef} />
      <Flights reduced={reduced} pulseRef={pulseRef} />
    </>
  );
}

const DiscoveryField = ({ className = '' }) => {
  const containerRef = useRef(null);
  const reduced = useReducedMotion();
  const active = useActive(containerRef);
  const isNarrow = typeof window !== 'undefined' && window.innerWidth < 640;
  const count = isNarrow ? 40 : 70;

  const frameloop = !active ? 'never' : reduced ? 'demand' : 'always';

  return (
    <div ref={containerRef} className={className} aria-hidden="true">
      <CanvasBoundary fallback={<StaticFallback />}>
        <Canvas
          dpr={1}
          frameloop={frameloop}
          gl={{ antialias: false, alpha: true, powerPreference: 'default', preserveDrawingBuffer: true }}
          camera={{ position: [0, 0, 8.5], fov: 42 }}
        >
          <Scene count={count} reduced={reduced} />
        </Canvas>
      </CanvasBoundary>
    </div>
  );
};

export default DiscoveryField;
