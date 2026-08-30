import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, ArrowRight, FlaskConical } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';
import { CHEMBL_OUTLIER, MODEL_FAMILIES } from './researchData';

const EvidenceRow = ({ label, value, tone }) => (
  <div className="flex items-center justify-between py-2.5 border-b border-paper-border/40 dark:border-white/[0.06] last:border-0">
    <span className="text-sm text-ink-soft dark:text-gray-400">{label}</span>
    <span
      className={`text-sm font-semibold ${
        tone === 'weak'
          ? 'text-rose-500 dark:text-rose-400'
          : tone === 'strong'
          ? 'text-teal-600 dark:text-teal-400'
          : 'text-ink dark:text-white'
      }`}
    >
      {value}
    </span>
  </div>
);

const EvidenceSection = () => {
  const [experimentRun, setExperimentRun] = useState(false);

  return (
    <section className="relative max-w-4xl px-4 mx-auto py-28" id="evidence">
      <SectionHeading eyebrow="Evidence intelligence">Every decision has evidence.</SectionHeading>

      <div className="grid gap-6 md:grid-cols-2">
        <div className={`${GLASS_PANEL} p-6`}>
          <div className="mb-1 text-xs font-semibold tracking-widest uppercase text-ink-soft dark:text-gray-400">
            Candidate
          </div>
          <div className="mb-4 font-mono text-lg font-bold text-ink dark:text-white">{CHEMBL_OUTLIER.id}</div>

          <EvidenceRow label={`${MODEL_FAMILIES.f1.name.split(' — ')[0]} rank`} value={`#${CHEMBL_OUTLIER.f1Rank} of ${CHEMBL_OUTLIER.totalCandidates}`} tone="weak" />
          <EvidenceRow label={`${MODEL_FAMILIES.f3.name.split(' — ')[0]} rank`} value={`#${CHEMBL_OUTLIER.f3Rank} of ${CHEMBL_OUTLIER.totalCandidates}`} tone="strong" />
          <EvidenceRow label="Structural novelty" value="No close analogue" />

          <div className="mt-5 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <div className="flex items-center gap-2 mb-1 text-sm font-semibold text-amber-600 dark:text-amber-400">
              <AlertTriangle className="w-4 h-4" /> Evidence disagreement
            </div>
            <p className="text-sm text-ink-soft dark:text-gray-300">
              Two cheap predictors disagree by 17 ranks about this chemical region.
            </p>
            <p className="mt-2 text-sm font-medium text-ink dark:text-white">Action: run the physics-based experiment.</p>
          </div>

          {!experimentRun && (
            <button
              onClick={() => setExperimentRun(true)}
              className="inline-flex items-center gap-2 mt-5 px-5 py-2.5 text-sm font-medium text-white rounded-full transition-transform hover:scale-105"
              style={{ background: 'linear-gradient(135deg, #4D432D, #8B5CF6)' }}
            >
              <FlaskConical className="w-4 h-4" /> Run Vina <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className={`${GLASS_PANEL} p-6 flex flex-col items-center justify-center text-center min-h-[280px]`}>
          <AnimatePresence mode="wait">
            {!experimentRun ? (
              <motion.p key="idle" exit={{ opacity: 0 }} className="text-sm text-ink-soft dark:text-gray-400">
                Waiting for the agent to allocate compute to this candidate.
              </motion.p>
            ) : (
              <motion.div key="result" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
                <div className="text-xs font-semibold tracking-widest uppercase text-ink-soft dark:text-gray-400">Vina</div>
                <div className="mt-2 text-4xl font-display font-bold text-clay-deep dark:text-violet-400">
                  {CHEMBL_OUTLIER.bindingAffinity} <span className="text-lg">kcal/mol</span>
                </div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                  className="mt-3 inline-block px-4 py-1.5 rounded-full text-sm font-medium bg-teal-500/10 text-teal-600 dark:text-teal-400"
                >
                  High surprise
                </motion.div>
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.9 }}
                  className="mt-3 text-sm font-medium text-ink dark:text-white"
                >
                  Model blind spot detected
                </motion.p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
};

export default EvidenceSection;
