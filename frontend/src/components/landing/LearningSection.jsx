import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { SectionHeading, ACCENT_GRADIENT, GLASS_PANEL } from './shared';

const STEPS = [
  'Prediction',
  'Experiment',
  'Observed result',
  'Prediction error',
  'Model disagreement',
  'Blind-spot hypothesis',
  'Strategy update',
  'Next candidates',
];

const LearningSection = () => (
  <section className="relative max-w-5xl px-4 mx-auto py-28">
    <SectionHeading eyebrow="Self-correction">When the model is wrong, DrugForge learns why.</SectionHeading>

    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.6 }}
      className="my-14 text-center"
    >
      <p className="font-display text-2xl sm:text-3xl md:text-4xl font-bold tracking-wide">
        <span className="text-ink dark:text-white">PREDICT</span>{' '}
        <span className="text-paper-border dark:text-gray-600">→</span>{' '}
        <span className="text-ink dark:text-white">TEST</span>{' '}
        <span className="text-paper-border dark:text-gray-600">→</span>{' '}
        <span className={ACCENT_GRADIENT}>SURPRISE</span>{' '}
        <span className="text-paper-border dark:text-gray-600">→</span>{' '}
        <span className={ACCENT_GRADIENT}>LEARN</span>
      </p>
    </motion.div>

    <div className="flex flex-wrap items-center justify-center gap-3">
      {STEPS.map((step, i) => (
        <React.Fragment key={step}>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.4, delay: i * 0.05 }}
            className={`${GLASS_PANEL} px-4 py-2.5 text-sm font-medium text-ink dark:text-white`}
          >
            {step}
          </motion.div>
          {i < STEPS.length - 1 && <ArrowRight className="w-4 h-4 text-paper-border dark:text-gray-600 shrink-0" />}
        </React.Fragment>
      ))}
    </div>

    <p className="max-w-2xl mx-auto mt-14 text-center text-ink-soft dark:text-gray-300">
      DrugForge does not treat every prediction as truth. Experimental outcomes can
      reveal where a model is unreliable, allowing future decisions to account for
      what the system has learned.
    </p>
  </section>
);

export default LearningSection;
