import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, FlaskConical } from 'lucide-react';
import DiscoveryField from './DiscoveryField';
import { ACCENT_GRADIENT } from './shared';
import { HERO_METRICS } from './researchData';

const Hero = () => (
  <section className="relative min-h-screen flex items-center overflow-hidden">
    <DiscoveryField className="fixed inset-0 -z-10 pointer-events-none" />

    <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-32 pb-20 w-full">
      <div className="max-w-2xl">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium tracking-widest uppercase border border-clay/25 dark:border-violet-500/20 bg-white/60 dark:bg-black/30 backdrop-blur-md text-clay-deep dark:text-violet-300">
            Agentic computational drug discovery
          </span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="mt-8 font-display font-bold tracking-tight text-ink dark:text-white text-4xl sm:text-5xl lg:text-6xl leading-[1.1] [text-shadow:0_2px_24px_rgba(252,252,252,0.8)] dark:[text-shadow:0_2px_24px_rgba(17,24,39,0.85)]"
        >
          Drug Discovery That{' '}
          <span className={ACCENT_GRADIENT}>Knows What It Doesn&apos;t Know.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="mt-6 text-lg leading-relaxed text-ink-soft dark:text-gray-300"
        >
          DrugForge combines molecular AI, ADMET prediction, structural reasoning, and
          physics-based docking into an adaptive discovery loop that decides where
          expensive computation is actually worth spending.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.35 }}
          className="flex flex-col items-center gap-4 mt-10 sm:flex-row sm:justify-start"
        >
          <Link
            to="/app/analyze"
            className="group inline-flex items-center gap-2 px-8 py-4 text-lg font-medium text-white rounded-full shadow-lg transition-transform hover:scale-[1.03]"
            style={{ background: 'linear-gradient(135deg, #4D432D, #8B5CF6)' }}
          >
            <FlaskConical className="w-5 h-5" />
            Launch DrugForge
            <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <a
            href="#discover"
            className="inline-flex items-center gap-2 px-8 py-4 text-lg font-medium rounded-full border border-ink/15 dark:border-white/10 text-ink dark:text-gray-200 bg-ink/[0.03] dark:bg-white/5 backdrop-blur-sm hover:bg-ink/[0.06] dark:hover:bg-white/10 hover:border-clay/50 dark:hover:border-violet-500/30 transition-colors"
          >
            Explore the science
          </a>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.55, duration: 0.6 }}
          className="grid max-w-lg grid-cols-2 gap-4 mt-14 sm:grid-cols-4"
        >
          {HERO_METRICS.map((m) => (
            <div
              key={m.label}
              className="text-center px-3 py-4 rounded-2xl border border-paper-border/50 dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.03] backdrop-blur-sm"
            >
              <div className={`text-lg md:text-xl font-bold font-display ${ACCENT_GRADIENT}`}>{m.value}</div>
              <div className="mt-1 text-[10px] tracking-[1.5px] text-ink-soft dark:text-gray-400 uppercase">{m.label}</div>
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  </section>
);

export default Hero;
