/**
 * BorderBeam — animated border that orbits around a container.
 *
 * Inspired by Magic UI's Border Beam.
 * A small bright dot travels along the border of any card or section,
 * creating a futuristic scanning/tracing effect.
 */

import React from "react";
import { cn } from "../../lib/utils";

export const BorderBeam = ({
  className,
  size = 200,
  duration = 12,
  delay = 0,
  colorFrom = "#06b6d4",
  colorTo = "#8b5cf6",
  borderWidth = 1.5,
}) => {
  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-0 rounded-[inherit]",
        className
      )}
      style={{
        "--border-beam-size": `${size}px`,
        "--border-beam-duration": `${duration}s`,
        "--border-beam-delay": `${delay}s`,
        "--border-beam-color-from": colorFrom,
        "--border-beam-color-to": colorTo,
        "--border-beam-width": `${borderWidth}px`,
      }}
    >
      <div
        className="absolute inset-0 rounded-[inherit]"
        style={{
          padding: `${borderWidth}px`,
          mask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
          maskComposite: "exclude",
          WebkitMaskComposite: "xor",
          background: `conic-gradient(from calc(var(--border-beam-angle, 0) * 1deg), transparent 60%, ${colorFrom}, ${colorTo}, transparent 80%)`,
          animation: `border-beam-spin var(--border-beam-duration) linear var(--border-beam-delay) infinite`,
        }}
      />
    </div>
  );
};

export default BorderBeam;
