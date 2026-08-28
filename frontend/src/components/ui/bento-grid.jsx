/**
 * BentoGrid — animated hover-glow grid layout for feature cards.
 *
 * Inspired by Aceternity UI's Bento Grid.
 * Each card tracks mouse position to create a radial glow
 * that follows the cursor, plus a subtle border light-sweep.
 */

import React, { useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { cn } from "../../lib/utils";

export const BentoGrid = ({ children, className }) => {
  return (
    <div
      className={cn(
        "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 max-w-7xl mx-auto",
        className
      )}
    >
      {children}
    </div>
  );
};

export const BentoGridItem = ({
  className,
  title,
  description,
  icon,
  accentColor = "cyan",
  index = 0,
}) => {
  const ref = useRef(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);

  const handleMouseMove = useCallback((e) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    setMousePosition({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  }, []);

  // Map color name to tailwind values
  const colorMap = {
    cyan: { glow: "rgba(6, 182, 212, 0.15)", border: "rgba(6, 182, 212, 0.4)", text: "text-cyan-400", bg: "bg-cyan-500/15", iconColor: "text-cyan-400" },
    violet: { glow: "rgba(139, 92, 246, 0.15)", border: "rgba(139, 92, 246, 0.4)", text: "text-violet-400", bg: "bg-violet-500/15", iconColor: "text-violet-400" },
    rose: { glow: "rgba(244, 63, 94, 0.15)", border: "rgba(244, 63, 94, 0.4)", text: "text-rose-400", bg: "bg-rose-500/15", iconColor: "text-rose-400" },
    amber: { glow: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.4)", text: "text-amber-400", bg: "bg-amber-500/15", iconColor: "text-amber-400" },
    teal: { glow: "rgba(20, 184, 166, 0.15)", border: "rgba(20, 184, 166, 0.4)", text: "text-teal-400", bg: "bg-teal-500/15", iconColor: "text-teal-400" },
    emerald: { glow: "rgba(16, 185, 129, 0.15)", border: "rgba(16, 185, 129, 0.4)", text: "text-emerald-400", bg: "bg-emerald-500/15", iconColor: "text-emerald-400" },
    sky: { glow: "rgba(14, 165, 233, 0.15)", border: "rgba(14, 165, 233, 0.4)", text: "text-sky-400", bg: "bg-sky-500/15", iconColor: "text-sky-400" },
  };

  const colors = colorMap[accentColor] || colorMap.cyan;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-50px" }}
      transition={{ duration: 0.5, delay: index * 0.07 }}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        "group relative rounded-2xl overflow-hidden",
        "border border-white/[0.08] dark:border-white/[0.08] border-gray-200/50",
        "bg-white/[0.03] dark:bg-white/[0.03] bg-gray-50/80",
        "p-6 transition-all duration-300",
        "hover:border-white/[0.15] dark:hover:border-white/[0.15] hover:border-gray-300/60",
        className
      )}
    >
      {/* Mouse-tracking radial glow */}
      <div
        className="absolute inset-0 transition-opacity duration-500 rounded-2xl pointer-events-none"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `radial-gradient(350px circle at ${mousePosition.x}px ${mousePosition.y}px, ${colors.glow}, transparent 60%)`,
        }}
      />

      {/* Hover border glow */}
      <div
        className="absolute inset-0 transition-opacity duration-500 rounded-2xl pointer-events-none"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `radial-gradient(400px circle at ${mousePosition.x}px ${mousePosition.y}px, ${colors.border}, transparent 50%)`,
          mask: "linear-gradient(black, black) content-box, linear-gradient(black, black)",
          maskComposite: "exclude",
          WebkitMaskComposite: "xor",
          padding: "1px",
          borderRadius: "1rem",
        }}
      />

      {/* Content */}
      <div className="relative z-10">
        {/* Icon */}
        <div
          className={cn(
            "w-12 h-12 rounded-xl mb-4 flex items-center justify-center",
            "transition-all duration-300",
            colors.bg,
            "group-hover:scale-110 group-hover:shadow-lg"
          )}
          style={{
            boxShadow: isHovered
              ? `0 0 25px ${colors.glow}, 0 0 50px ${colors.glow}`
              : "none",
          }}
        >
          {icon}
        </div>

        {/* Title */}
        <h3
          className={cn(
            "text-lg font-semibold mb-2 transition-colors duration-300",
            "text-gray-800 dark:text-gray-100",
            `group-hover:${colors.text}`
          )}
        >
          {title}
        </h3>

        {/* Description */}
        <p className="text-sm leading-relaxed text-gray-500 dark:text-gray-400">
          {description}
        </p>
      </div>

      {/* Bottom shimmer line on hover */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px transition-opacity duration-500"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `linear-gradient(90deg, transparent, ${colors.border}, transparent)`,
        }}
      />
    </motion.div>
  );
};

export default BentoGrid;
