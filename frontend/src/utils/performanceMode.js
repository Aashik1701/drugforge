/**
 * Reads the performance-mode flag set once at app init (src/index.jsx).
 * Use to gate continuous JS-driven animations (framer-motion `repeat:
 * Infinity` loops) that the CSS-only override in index.css can't reach —
 * CSS animation classes are handled there instead, this is only for the
 * JS-driven exception.
 */
export function isPerformanceMode() {
  if (typeof document === 'undefined') return false;
  return document.documentElement.dataset.performanceMode === 'true';
}
