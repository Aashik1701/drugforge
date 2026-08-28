/**
 * HeavyComputeConfirm — confirmation modal shown before a HEAVY_LOCAL job
 * (docking) is submitted. Per spec §12: no fake time estimates — if we
 * don't have a real one, we say so rather than inventing a number.
 */
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { GlassButton } from './ui/GlassCard';

const HeavyComputeConfirm = ({
  open,
  target,
  exhaustiveness,
  maxConcurrent,
  onCancel,
  onConfirm,
  confirming = false,
}) => {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onCancel}
        >
          <motion.div
            className="w-full max-w-md p-6 border rounded-2xl bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl border-white/20"
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Heavy Computation</h3>
            </div>
            <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
              AutoDock Vina will run a real physics-based docking search. This uses significant CPU
              and is not instant.
            </p>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 mb-4 text-sm">
              <dt className="text-gray-500 dark:text-gray-400">Target</dt>
              <dd className="text-right font-mono uppercase">{target}</dd>
              <dt className="text-gray-500 dark:text-gray-400">Exhaustiveness</dt>
              <dd className="text-right font-mono">{exhaustiveness}</dd>
              <dt className="text-gray-500 dark:text-gray-400">Max Concurrent Jobs</dt>
              <dd className="text-right font-mono">{maxConcurrent ?? '—'}</dd>
              <dt className="text-gray-500 dark:text-gray-400">Estimated Duration</dt>
              <dd className="text-right text-gray-500 dark:text-gray-400 italic">not available</dd>
            </dl>

            <div className="flex justify-end gap-2">
              <GlassButton variant="ghost" onClick={onCancel} disabled={confirming}>
                Cancel
              </GlassButton>
              <GlassButton variant="primary" onClick={onConfirm} disabled={confirming}>
                {confirming ? 'Starting…' : 'Run Docking'}
              </GlassButton>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default HeavyComputeConfirm;
