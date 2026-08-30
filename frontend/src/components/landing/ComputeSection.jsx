import React from 'react';
import { motion } from 'framer-motion';
import { ArrowDown } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';
import { COMPUTE_TIERS } from './researchData';

const costColor = { Low: 'text-teal-600 dark:text-teal-400', High: 'text-rose-500 dark:text-rose-400' };

const ComputeSection = () => (
  <section className="relative max-w-4xl px-4 mx-auto py-28">
    <SectionHeading eyebrow="Compute intelligence">Spend computation where it matters.</SectionHeading>

    <p className="max-w-2xl mx-auto -mt-8 mb-4 text-center text-ink-soft dark:text-gray-300">
      Expensive computation is deliberate, bounded, and isolated instead of running
      indiscriminately — the same routing and budget logic that already keeps
      DrugForge&apos;s prediction endpoints responsive during heavy docking jobs.
    </p>
    <p className="mb-14 text-xs text-center text-ink-soft/70 dark:text-gray-500">
      Compute unit counts below are illustrative, not measured figures.
    </p>

    <div className="text-center mb-6">
      <div className={`${GLASS_PANEL} inline-block px-8 py-3`}>
        <div className="text-xs tracking-widest uppercase text-ink-soft dark:text-gray-400">Compute budget</div>
        <div className="text-2xl font-display font-bold text-ink dark:text-white">500 units</div>
      </div>
    </div>
    <ArrowDown className="w-5 h-5 mx-auto mb-6 text-paper-border dark:text-gray-600" />

    <div className="grid gap-4 sm:grid-cols-3">
      {COMPUTE_TIERS.map((tier, i) => (
        <motion.div
          key={tier.name}
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.5, delay: i * 0.1 }}
          className={`${GLASS_PANEL} p-6 text-center`}
        >
          <div className="font-display text-lg font-bold text-ink dark:text-white">{tier.name}</div>
          <div className={`mt-1 text-sm font-semibold ${costColor[tier.cost]}`}>{tier.cost} cost</div>
          <p className="mt-3 text-sm text-ink-soft dark:text-gray-400">{tier.role}</p>
        </motion.div>
      ))}
    </div>

    <ArrowDown className="w-5 h-5 mx-auto mt-6 mb-4 text-paper-border dark:text-gray-600" />
    <div className={`${GLASS_PANEL} max-w-xs mx-auto px-6 py-3 text-center font-semibold text-ink dark:text-white`}>
      Agent decision
    </div>
  </section>
);

export default ComputeSection;
