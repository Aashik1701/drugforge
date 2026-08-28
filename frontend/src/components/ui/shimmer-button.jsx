/**
 * ShimmerButton — CTA button with a sweeping light shimmer effect.
 *
 * Inspired by Magic UI's Shimmer Button.
 * A diagonal light band continuously sweeps across the button surface.
 * Supports primary (cyan→violet gradient) and ghost variants.
 */

import React from "react";
import { motion } from "framer-motion";
import { cn } from "../../lib/utils";

export const ShimmerButton = React.forwardRef(
  (
    {
      children,
      className,
      shimmerColor = "rgba(255, 255, 255, 0.15)",
      shimmerSize = "0.1em",
      shimmerDuration = "2.5s",
      background = "linear-gradient(135deg, #06b6d4, #8b5cf6)",
      borderRadius = "9999px",
      as: Component = "button",
      ...props
    },
    ref
  ) => {
    return (
      <motion.div
        whileHover={{ scale: 1.04, y: -2 }}
        whileTap={{ scale: 0.97 }}
        className="relative inline-block"
      >
        <Component
          ref={ref}
          className={cn(
            "group relative z-10 inline-flex items-center justify-center overflow-hidden",
            "px-10 py-4 text-lg font-medium text-white",
            "transition-all duration-300",
            "shadow-lg hover:shadow-xl",
            className
          )}
          style={{
            background,
            borderRadius,
          }}
          {...props}
        >
          {/* Shimmer sweep */}
          <div
            className="absolute inset-0 overflow-hidden"
            style={{ borderRadius }}
          >
            <div
              className="absolute inset-0 animate-shimmer-sweep"
              style={{
                background: `linear-gradient(
                  110deg,
                  transparent 25%,
                  ${shimmerColor} 45%,
                  ${shimmerColor} 55%,
                  transparent 75%
                )`,
                backgroundSize: "250% 100%",
              }}
            />
          </div>

          {/* Glow aura behind button */}
          <div
            className="absolute -inset-1 rounded-full opacity-0 transition-opacity duration-300 blur-xl group-hover:opacity-60"
            style={{ background }}
          />

          {/* Inner highlight (top edge) */}
          <div
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent"
          />

          {/* Text */}
          <span className="relative z-10 flex items-center gap-2">{children}</span>
        </Component>
      </motion.div>
    );
  }
);

ShimmerButton.displayName = "ShimmerButton";

/**
 * GhostShimmerButton — transparent variant with border glow.
 */
export const GhostShimmerButton = React.forwardRef(
  ({ children, className, ...props }, ref) => {
    return (
      <motion.div
        whileHover={{ scale: 1.04, y: -2 }}
        whileTap={{ scale: 0.97 }}
        className="relative inline-block"
      >
        <button
          ref={ref}
          className={cn(
            "group relative inline-flex items-center justify-center overflow-hidden",
            "px-8 py-4 text-lg font-medium rounded-full",
            "text-gray-700 dark:text-gray-200",
            "border border-white/20 dark:border-white/10",
            "bg-white/5 dark:bg-white/5 backdrop-blur-sm",
            "hover:bg-white/10 dark:hover:bg-white/10",
            "hover:border-cyan-500/30",
            "transition-all duration-300",
            className
          )}
          {...props}
        >
          {/* Subtle shimmer */}
          <div className="absolute inset-0 overflow-hidden rounded-full">
            <div
              className="absolute inset-0 animate-shimmer-sweep"
              style={{
                background: `linear-gradient(
                  110deg,
                  transparent 30%,
                  rgba(6,182,212,0.08) 47%,
                  rgba(139,92,246,0.08) 53%,
                  transparent 70%
                )`,
                backgroundSize: "250% 100%",
              }}
            />
          </div>

          <span className="relative z-10 flex items-center gap-2">{children}</span>
        </button>
      </motion.div>
    );
  }
);

GhostShimmerButton.displayName = "GhostShimmerButton";

export default ShimmerButton;
