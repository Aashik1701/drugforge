import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';
import { DOCKING_PIPELINE } from './researchData';

const DockingSection = () => (
  <section className="relative max-w-5xl px-4 mx-auto py-28">
    <SectionHeading eyebrow="Real physics">When prediction isn&apos;t enough, run the experiment.</SectionHeading>

    <div className="flex flex-wrap items-center justify-center gap-3 mb-12">
      {DOCKING_PIPELINE.map((step, i) => (
        <React.Fragment key={step}>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.4, delay: i * 0.06 }}
            className={`${GLASS_PANEL} px-4 py-2.5 text-sm font-medium text-ink dark:text-white`}
          >
            {step}
          </motion.div>
          {i < DOCKING_PIPELINE.length - 1 && (
            <ArrowRight className="w-4 h-4 text-paper-border dark:text-gray-600 shrink-0" />
          )}
        </React.Fragment>
      ))}
    </div>

    <div className="max-w-2xl mx-auto text-center">
      <p className="text-xl font-semibold text-ink dark:text-white">Real AutoDock Vina docking.</p>
      <p className="mt-4 text-ink-soft dark:text-gray-300">
        Vina is a physics-based docking engine, not an AI model — it estimates a
        binding pose and a docking score from molecular structure and force-field
        physics. A docking score is structural evidence, not a guarantee of true
        binding affinity; it is one more, more expensive, source of evidence in the
        agent&apos;s decision.
      </p>
    </div>
  </section>
);

export default DockingSection;
