import React from 'react';

// Small "AI" accent gradient reused across landing sections. Light: clay →
// violet. Dark: violet → teal.
export const ACCENT_GRADIENT =
  'bg-gradient-to-r from-clay-deep to-violet-600 dark:from-violet-400 dark:to-teal-400 bg-clip-text text-transparent';

export const SectionEyebrow = ({ children }) => (
  <span className="inline-flex items-center mb-5 px-3.5 py-1.5 rounded-full text-xs font-medium tracking-wide border border-clay/25 dark:border-violet-500/20 bg-white/60 dark:bg-black/30 backdrop-blur-md text-clay-deep dark:text-violet-300">
    {children}
  </span>
);

export const SectionHeading = ({ eyebrow, children, className = '', center = true }) => (
  <div className={`${center ? 'text-center' : ''} mb-14 ${className}`}>
    {eyebrow && <SectionEyebrow>{eyebrow}</SectionEyebrow>}
    <h2 className="font-display text-3xl sm:text-4xl md:text-5xl font-bold text-ink dark:text-white [text-shadow:0_2px_20px_rgba(252,252,252,0.9)] dark:[text-shadow:0_2px_20px_rgba(17,24,39,0.9)]">
      {children}
    </h2>
  </div>
);

// Glass panel — the standard translucent card surface used throughout the
// new sections so the DiscoveryField canvas stays visible behind content.
export const GLASS_PANEL =
  'rounded-2xl border border-paper-border/60 dark:border-white/[0.08] bg-white/85 dark:bg-white/[0.04] backdrop-blur-md';
