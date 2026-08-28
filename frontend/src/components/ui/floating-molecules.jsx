/**
 * FloatingMolecules — decorative floating atom/molecule shapes.
 *
 * Renders SVG molecular illustrations (benzene ring, atom orbits, bonds)
 * that drift slowly across the hero section for a scientific feel.
 */

import React from "react";
import { motion } from "framer-motion";
import { isPerformanceMode } from "../../utils/performanceMode";

/* ── Individual shapes ──────────────────────────────────── */

const HexRing = ({ size = 40, color = "cyan", delay = 0, x, y }) => (
  <motion.svg
    width={size}
    height={size}
    viewBox="0 0 40 40"
    fill="none"
    className="absolute pointer-events-none"
    style={{ left: x, top: y }}
    initial={{ opacity: 0, scale: 0.5 }}
    animate={{
      opacity: [0, 0.35, 0.2, 0.35, 0],
      scale: [0.8, 1, 1.05, 1, 0.8],
      y: [0, -30, -60],
      rotate: [0, 90, 180],
    }}
    transition={{
      duration: 18,
      delay,
      repeat: Infinity,
      ease: "easeInOut",
    }}
  >
    <polygon
      points="20,2 36,11 36,29 20,38 4,29 4,11"
      stroke={color === "cyan" ? "#06b6d4" : color === "violet" ? "#8b5cf6" : "#14b8a6"}
      strokeWidth="1.5"
      fill="none"
      opacity="0.6"
    />
    {/* Centre dot */}
    <circle
      cx="20"
      cy="20"
      r="2"
      fill={color === "cyan" ? "#06b6d4" : color === "violet" ? "#8b5cf6" : "#14b8a6"}
      opacity="0.5"
    />
  </motion.svg>
);

const AtomOrbit = ({ size = 56, delay = 0, x, y }) => (
  <motion.svg
    width={size}
    height={size}
    viewBox="0 0 56 56"
    fill="none"
    className="absolute pointer-events-none"
    style={{ left: x, top: y }}
    initial={{ opacity: 0 }}
    animate={{
      opacity: [0, 0.3, 0.15, 0.3, 0],
      rotate: [0, 360],
    }}
    transition={{
      duration: 24,
      delay,
      repeat: Infinity,
      ease: "linear",
    }}
  >
    {/* Nucleus */}
    <circle cx="28" cy="28" r="3" fill="#8b5cf6" opacity="0.6" />
    {/* Orbits */}
    <ellipse cx="28" cy="28" rx="24" ry="10" stroke="#06b6d4" strokeWidth="0.8" opacity="0.3" />
    <ellipse cx="28" cy="28" rx="24" ry="10" stroke="#8b5cf6" strokeWidth="0.8" opacity="0.3"
      transform="rotate(60 28 28)" />
    <ellipse cx="28" cy="28" rx="24" ry="10" stroke="#14b8a6" strokeWidth="0.8" opacity="0.3"
      transform="rotate(120 28 28)" />
    {/* Electrons */}
    <circle cx="52" cy="28" r="2" fill="#06b6d4" opacity="0.7" />
  </motion.svg>
);

const BondLine = ({ delay = 0, x, y, angle = 0 }) => (
  <motion.div
    className="absolute w-12 h-px pointer-events-none"
    style={{
      left: x,
      top: y,
      background: "linear-gradient(90deg, transparent, rgba(6,182,212,0.3), transparent)",
      transform: `rotate(${angle}deg)`,
    }}
    initial={{ opacity: 0 }}
    animate={{
      opacity: [0, 0.4, 0.2, 0.4, 0],
      scaleX: [0.5, 1, 0.7, 1, 0.5],
    }}
    transition={{
      duration: 14,
      delay,
      repeat: Infinity,
      ease: "easeInOut",
    }}
  />
);

const FloatingDot = ({ delay = 0, x, y, color = "#06b6d4" }) => (
  <motion.div
    className="absolute w-1.5 h-1.5 rounded-full pointer-events-none"
    style={{ left: x, top: y, backgroundColor: color }}
    initial={{ opacity: 0 }}
    animate={{
      opacity: [0, 0.6, 0.3, 0.6, 0],
      y: [0, -20, -40],
      x: [0, 5, -5],
    }}
    transition={{
      duration: 12,
      delay,
      repeat: Infinity,
      ease: "easeInOut",
    }}
  />
);

/* ── Composition ────────────────────────────────────────── */

export const FloatingMolecules = () => {
  // Continuous framer-motion loops (repeat: Infinity below) aren't reachable
  // by the CSS-only performance-mode override in index.css — gate here
  // instead. Purely decorative, safe to skip entirely.
  if (isPerformanceMode()) return null;

  return (
  <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
    {/* Left cluster */}
    <HexRing x="8%" y="20%" color="cyan" delay={0} size={36} />
    <AtomOrbit x="5%" y="55%" delay={3} size={50} />
    <BondLine x="12%" y="40%" delay={1.5} angle={30} />
    <FloatingDot x="15%" y="30%" delay={2} color="#06b6d4" />
    <FloatingDot x="10%" y="65%" delay={5} color="#8b5cf6" />

    {/* Right cluster */}
    <HexRing x="85%" y="25%" color="violet" delay={4} size={32} />
    <AtomOrbit x="82%" y="60%" delay={7} size={44} />
    <BondLine x="88%" y="45%" delay={6} angle={-20} />
    <FloatingDot x="90%" y="35%" delay={8} color="#14b8a6" />
    <FloatingDot x="83%" y="70%" delay={3.5} color="#06b6d4" />

    {/* Scattered extras */}
    <HexRing x="25%" y="75%" color="teal" delay={9} size={28} />
    <HexRing x="70%" y="15%" color="cyan" delay={6} size={24} />
    <FloatingDot x="40%" y="85%" delay={7} color="#8b5cf6" />
    <FloatingDot x="65%" y="80%" delay={10} color="#14b8a6" />
    <BondLine x="72%" y="78%" delay={4} angle={60} />
  </div>
  );
};

export default FloatingMolecules;
