/**
 * AuroraBackground — animated gradient aurora effect for hero sections.
 *
 * Inspired by Aceternity UI's Aurora Background.
 * Uses CSS keyframe animations on layered radial gradients
 * to create a slowly morphing northern-lights effect.
 *
 * Layers (back → front):
 *  1. Dot-grid pattern       — subtle depth texture
 *  2. Aurora gradient band   — animated color wash
 *  3. Gradient mesh blobs    — slow-moving focus orbs
 *  4. Radial vignette mask   — draws eye to center
 *  5. Noise grain overlay    — film-grain texture
 *  6. Content (z-10)
 */

import React from "react";
import { cn } from "../../lib/utils";

export const AuroraBackground = ({
  children,
  className,
  showRadialGradient = true,
  showGrid = true,
}) => {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center transition-bg overflow-hidden",
        className
      )}
    >
      {/* ── Layer 1: Dot-grid texture ───────────────────── */}
      {showGrid && (
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.035] dark:opacity-[0.06]"
          style={{
            backgroundImage:
              "radial-gradient(circle, currentColor 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />
      )}

      {/* ── Layer 2: Aurora gradient band ───────────────── */}
      <div className="absolute inset-0 overflow-hidden">
        <div
          className={cn(
            `
            [--aurora:repeating-linear-gradient(100deg,theme(colors.cyan.500)_10%,theme(colors.violet.300)_15%,theme(colors.cyan.300)_20%,theme(colors.violet.200)_25%,theme(colors.cyan.400)_30%)]
            [background-image:var(--aurora)]
            [background-size:300%_200%]
            [background-position:50%_50%]
            filter blur-[60px]
            after:content-[""]
            after:absolute after:inset-0
            after:[background-image:var(--aurora)]
            after:[background-size:200%_100%]
            after:animate-aurora after:[background-attachment:fixed]
            after:mix-blend-soft-light
            pointer-events-none
            absolute -inset-[10px]
            opacity-40 dark:opacity-30
            will-change-transform
            `,
            showRadialGradient &&
              `[mask-image:radial-gradient(ellipse_80%_50%_at_50%_-20%,black_40%,transparent_100%)]`
          )}
        />
      </div>

      {/* ── Layer 3: Gradient mesh orbs ─────────────────── */}
      <div
        className="absolute rounded-full w-[500px] h-[500px] bg-cyan-500/20 blur-[100px] animate-aurora-orb-1"
        style={{ top: "5%", left: "10%" }}
      />
      <div
        className="absolute rounded-full w-[420px] h-[420px] bg-violet-500/15 blur-[100px] animate-aurora-orb-2"
        style={{ top: "25%", right: "5%" }}
      />
      <div
        className="absolute rounded-full w-[350px] h-[350px] bg-teal-500/10 blur-[80px] animate-aurora-orb-3"
        style={{ bottom: "10%", left: "25%" }}
      />

      {/* Centre spotlight glow (behind title) */}
      <div
        className="absolute left-1/2 top-[38%] -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] rounded-full pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(6,182,212,0.12) 0%, rgba(139,92,246,0.08) 40%, transparent 70%)",
        }}
      />

      {/* ── Layer 4: Vignette mask ──────────────────────── */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 50%, transparent 50%, rgba(15,23,42,0.45) 100%)",
        }}
      />

      {/* ── Layer 5: Noise grain ────────────────────────── */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.025] dark:opacity-[0.04] mix-blend-overlay"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E")`,
          backgroundRepeat: "repeat",
          backgroundSize: "128px 128px",
        }}
      />

      {/* ── Content ─────────────────────────────────────── */}
      <div className="relative z-10 w-full">{children}</div>
    </div>
  );
};

export default AuroraBackground;
