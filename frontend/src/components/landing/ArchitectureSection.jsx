import React from 'react';
import { motion } from 'framer-motion';
import { ArrowDown, RotateCcw } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';

const Node = ({ children, delay = 0, tone = 'default' }) => (
  <motion.div
    initial={{ opacity: 0, y: 12 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: '-60px' }}
    transition={{ duration: 0.5, delay }}
    className={`${GLASS_PANEL} px-4 py-3 text-sm font-semibold text-center ${
      tone === 'accent' ? 'text-clay-deep dark:text-violet-400' : 'text-ink dark:text-white'
    }`}
  >
    {children}
  </motion.div>
);

const Arrow = () => <ArrowDown className="w-4 h-4 mx-auto my-2 text-paper-border dark:text-gray-600" />;

const ArchitectureSection = () => (
  <section className="relative max-w-4xl px-4 mx-auto py-28">
    <SectionHeading eyebrow="System architecture">From prediction to adaptive experimentation.</SectionHeading>

    <div className="max-w-xs mx-auto">
      <Node tone="accent">DrugForge Agent</Node>
      <Arrow />
    </div>

    <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
      <Node delay={0.05}>Scientific Goal</Node>
      <Node delay={0.1}>Compute Budget</Node>
    </div>
    <Arrow />

    <div className="max-w-xs mx-auto">
      <Node delay={0.15}>Evidence Engine</Node>
    </div>
    <Arrow />

    <div className="grid grid-cols-3 gap-3 max-w-lg mx-auto">
      <Node delay={0.2}>RDKit</Node>
      <Node delay={0.25}>ML models</Node>
      <Node delay={0.3}>Vina</Node>
    </div>
    <Arrow />

    <div className="max-w-xs mx-auto">
      <Node delay={0.35}>Decision Engine</Node>
    </div>
    <Arrow />

    <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
      <Node delay={0.4} tone="accent">Exploit</Node>
      <Node delay={0.42} tone="accent">Explore</Node>
    </div>

    <div className="max-w-xs mx-auto mt-1">
      <p className="text-xs text-center text-ink-soft/70 dark:text-gray-500 mb-1">from Explore</p>
      <Arrow />
      <Node delay={0.5}>Experiment</Node>
      <Arrow />
      <Node delay={0.55}>Observe</Node>
      <Arrow />
      <Node delay={0.6}>Learn / Update</Node>
    </div>

    <motion.div
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
      transition={{ delay: 0.7, duration: 0.5 }}
      className="flex items-center justify-center gap-2 mt-6 text-sm text-ink-soft dark:text-gray-400"
    >
      <RotateCcw className="w-4 h-4" /> Feeds back into the next decision
    </motion.div>
  </section>
);

export default ArchitectureSection;
