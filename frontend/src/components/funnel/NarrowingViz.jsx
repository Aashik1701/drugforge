import React from 'react';
import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { normalizeStages } from '../../utils/funnelState';

/**
 * The whole point of the screen: the candidate set narrowing, stage by stage,
 * as the counts arrive. 45 -> 45 -> 41 -> 41 -> N. Each gate fills in when its
 * count lands; the bar under the row shrinks with the survivor fraction.
 */
export default function NarrowingViz({ candidatesIn = 0, stageSurvivors = [], budgetN, docked }) {
  const stages = normalizeStages(stageSurvivors);
  // synthetic first gate: everything in
  const gates = [
    { key: 'input', label: 'candidates', value: candidatesIn, dropped: null, done: candidatesIn > 0 },
    ...stages.map((s) => ({
      key: s.stage,
      label: s.label,
      value: s.out,
      dropped: s.in - s.out,
      done: true,
    })),
  ];
  // the dock gate: shown as pending until the run reports it
  const dockReported = stages.some((s) => s.stage === 'dock_top_n');
  if (!dockReported) {
    gates.push({
      key: 'dock',
      label: 'docked',
      value: docked ?? budgetN,
      dropped: null,
      done: docked != null,
      pending: docked == null,
    });
  }

  const denom = candidatesIn || 1;

  return (
    <div>
      <div className="flex flex-wrap items-stretch gap-2">
        {gates.map((g, i) => (
          <React.Fragment key={g.key}>
            {i > 0 && (
              <div className="flex items-center text-gray-300 dark:text-gray-600">
                <ChevronRight className="h-4 w-4" />
              </div>
            )}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: g.done ? 1 : 0.45, y: 0 }}
              transition={{ duration: 0.3 }}
              className={`relative min-w-[92px] flex-1 rounded-xl border px-3 py-2.5 text-center
                ${g.pending
                  ? 'border-dashed border-gray-300 bg-white/5 dark:border-gray-600'
                  : 'border-white/20 bg-white/10 dark:bg-black/20'}`}
            >
              <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">{g.label}</div>
              <div className="mt-0.5 font-mono text-2xl font-semibold text-gray-800 dark:text-gray-100 tabular-nums">
                {g.pending ? '…' : g.value}
              </div>
              {g.dropped != null && g.dropped > 0 && (
                <div className="text-[10px] font-medium text-rose-500">-{g.dropped}</div>
              )}
              {g.dropped === 0 && <div className="text-[10px] text-gray-400">-0</div>}
            </motion.div>
          </React.Fragment>
        ))}
      </div>

      {/* survivor bar */}
      <div className="mt-3 flex h-2 gap-1 overflow-hidden rounded-full bg-gray-200/60 dark:bg-gray-700/50">
        {gates
          .filter((g) => !g.pending && g.value != null)
          .map((g) => (
            <motion.div
              key={g.key}
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(4, (g.value / denom) * 100)}%` }}
              transition={{ duration: 0.4 }}
              className={`h-full rounded-full ${g.key === 'input' ? 'bg-gray-400/70' : g.key === 'dock' ? 'bg-teal-400' : 'bg-violet-400/70'}`}
              style={{ maxWidth: `${(g.value / denom) * 100}%` }}
              title={`${g.label}: ${g.value} of ${denom}`}
            />
          ))}
      </div>
    </div>
  );
}
