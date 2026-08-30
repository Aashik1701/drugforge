import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowDown, FlaskConical, Gauge } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';
import { CHEMBL_OUTLIER } from './researchData';

const ProblemSection = () => {
  const [revealed, setRevealed] = useState(false);

  return (
    <section className="relative px-4 mx-auto py-28 max-w-5xl" id="discover">
      <SectionHeading eyebrow="The problem">Prediction isn&apos;t the same as understanding.</SectionHeading>

      <p className="max-w-2xl mx-auto -mt-8 mb-12 text-center text-ink-soft dark:text-gray-300">
        One real candidate from DrugForge&apos;s own research set,{' '}
        <code className="px-1.5 py-0.5 rounded bg-ink/5 dark:bg-white/10 text-sm">{CHEMBL_OUTLIER.id}</code>.
      </p>

      <div className="grid gap-6 md:grid-cols-2">
        <div className={`${GLASS_PANEL} p-8 text-center`}>
          <div className="flex items-center justify-center gap-2 mb-4 text-xs font-semibold tracking-widest uppercase text-ink-soft dark:text-gray-400">
            <Gauge className="w-4 h-4" /> Cheap prediction
          </div>
          <p className="text-sm text-ink-soft dark:text-gray-400 mb-6">Ligand-only model (ECFP4 + descriptors)</p>
          <div className="text-5xl font-display font-bold text-ink dark:text-white">#{CHEMBL_OUTLIER.f1Rank}</div>
          <div className="mt-1 text-sm text-ink-soft dark:text-gray-400">of {CHEMBL_OUTLIER.totalCandidates} candidates</div>
          <div className="mt-6 inline-block px-4 py-1.5 rounded-full text-sm font-medium bg-rose-500/10 text-rose-500 dark:text-rose-400">
            Low priority
          </div>
        </div>

        <div className={`${GLASS_PANEL} p-8 text-center relative overflow-hidden`}>
          <div className="flex items-center justify-center gap-2 mb-4 text-xs font-semibold tracking-widest uppercase text-ink-soft dark:text-gray-400">
            <FlaskConical className="w-4 h-4" /> Physics-based docking
          </div>
          <p className="text-sm text-ink-soft dark:text-gray-400 mb-6">Real AutoDock Vina result</p>

          {!revealed ? (
            <button
              onClick={() => setRevealed(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 mt-2 mb-2 text-sm font-medium text-white rounded-full transition-transform hover:scale-105"
              style={{ background: 'linear-gradient(135deg, #4D432D, #8B5CF6)' }}
            >
              Run the physics-based experiment <ArrowDown className="w-4 h-4" />
            </button>
          ) : (
            <AnimatePresence>
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
                <div className="text-5xl font-display font-bold text-clay-deep dark:text-violet-400">
                  {CHEMBL_OUTLIER.bindingAffinity} <span className="text-xl">kcal/mol</span>
                </div>
                <div className="mt-1 text-sm text-ink-soft dark:text-gray-400">
                  {CHEMBL_OUTLIER.affinityMargin} kcal/mol above the #2 hit
                </div>
                <div className="mt-6 inline-block px-4 py-1.5 rounded-full text-sm font-medium bg-teal-500/10 text-teal-600 dark:text-teal-400">
                  #{CHEMBL_OUTLIER.baselineRank} baseline hit
                </div>
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </div>

      <p className="max-w-2xl mx-auto mt-12 text-lg font-medium text-center text-ink dark:text-white">
        A model can be confident and still be wrong. DrugForge is designed around that reality.
      </p>
      <p className="max-w-xl mx-auto mt-3 text-sm text-center text-ink-soft dark:text-gray-400">
        This isn&apos;t a failure of any one model — it&apos;s why multiple, disagreeing evidence
        sources matter more than a single confident number.
      </p>
    </section>
  );
};

export default ProblemSection;
