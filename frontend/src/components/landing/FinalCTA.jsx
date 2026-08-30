import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { BorderBeam } from '../ui/border-beam';
import { ACCENT_GRADIENT, GLASS_PANEL } from './shared';

const FinalCTA = () => (
  <section className="px-4 py-32 text-center relative">
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.7 }}
      className="relative max-w-3xl mx-auto"
    >
      <div className={`${GLASS_PANEL} relative overflow-hidden p-16`}>
        <BorderBeam size={250} duration={14} colorFrom="#4D432D" colorTo="#8B5CF6" />

        <h2 className="relative mb-5 font-display text-4xl font-bold text-ink md:text-5xl dark:text-white">
          Give DrugForge a <span className={ACCENT_GRADIENT}>scientific question</span>.
        </h2>
        <p className="relative max-w-xl mx-auto mb-10 text-lg leading-relaxed text-ink-soft dark:text-gray-300">
          Let the system decide what to predict, what to question, and where
          computation is worth spending.
        </p>
        <div className="relative flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
          <Link
            to="/app/analyze"
            className="inline-flex items-center gap-2 px-8 py-4 text-lg font-medium text-white rounded-full shadow-lg transition-transform hover:scale-[1.03]"
            style={{ background: 'linear-gradient(135deg, #4D432D, #8B5CF6)' }}
          >
            Launch DrugForge <ArrowRight className="w-5 h-5" />
          </Link>
          <Link
            to="/research"
            className="inline-flex items-center gap-2 px-8 py-4 text-lg font-medium rounded-full border border-ink/15 dark:border-white/10 text-ink dark:text-gray-200 bg-ink/[0.03] dark:bg-white/5 hover:bg-ink/[0.06] dark:hover:bg-white/10 transition-colors"
          >
            Explore the methodology
          </Link>
        </div>
      </div>
    </motion.div>
  </section>
);

export default FinalCTA;
