/**
 * ComputeControl — lets the user pick the active compute mode and see what
 * it currently allows. The mode selector is a REAL control (calls
 * POST /api/compute/mode); the "Allow Docking / Allow Large Batches /
 * Allow Parallel Jobs / Max Concurrent" readout below it is informational,
 * not independently settable — each mode is one of three fixed, safe
 * presets (see backend/app/compute/policy.py). The backend enforces these
 * limits regardless of what this UI shows; it isn't a security boundary.
 */
import React from 'react';
import { GlassPanel, GlassBadge } from './ui/GlassCard';
import { useComputePolicy, useSetComputeMode } from '../hooks/useComputePolicy';

const MODES = [
  { value: 'battery-saver', label: 'Battery Saver', description: 'Predictions & chemistry only. Docking disabled.' },
  { value: 'balanced', label: 'Balanced', description: 'Docking allowed, one job at a time.' },
  { value: 'performance', label: 'Performance', description: 'Higher concurrency. Still has hard limits — never unlimited.' },
];

const ComputeControl = ({ className = '' }) => {
  const { data: policy, isLoading } = useComputePolicy();
  const setMode = useSetComputeMode();

  return (
    <GlassPanel className={`p-5 ${className}`}>
      <h3 className="mb-3 text-sm font-semibold tracking-wide text-gray-700 uppercase dark:text-gray-300">
        Compute Control
      </h3>

      <div className="space-y-2">
        {MODES.map((m) => {
          const active = policy?.mode === m.value;
          return (
            <button
              key={m.value}
              type="button"
              disabled={setMode.isPending}
              onClick={() => setMode.mutate(m.value)}
              className={`w-full text-left px-4 py-2.5 rounded-lg border transition-all duration-150 disabled:opacity-50
                ${active
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-700 dark:text-cyan-300'
                  : 'bg-white/10 border-white/20 text-gray-700 dark:text-gray-300 hover:bg-white/20'}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{m.label}</span>
                {active && <GlassBadge variant="success">Active</GlassBadge>}
              </div>
              <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{m.description}</p>
            </button>
          );
        })}
      </div>

      {!isLoading && policy && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-4 pt-4 border-t border-white/10 text-xs">
          <dt className="text-gray-500 dark:text-gray-400">Allow Docking</dt>
          <dd className="text-right font-mono">{policy.allow_docking ? 'yes' : 'no'}</dd>
          <dt className="text-gray-500 dark:text-gray-400">Allow Large Batches</dt>
          <dd className="text-right font-mono">{policy.allow_large_batches ? 'yes' : 'no'}</dd>
          <dt className="text-gray-500 dark:text-gray-400">Allow Parallel Jobs</dt>
          <dd className="text-right font-mono">{policy.allow_parallel_jobs ? 'yes' : 'no'}</dd>
          <dt className="text-gray-500 dark:text-gray-400">Max Concurrent Docking</dt>
          <dd className="text-right font-mono">{policy.max_docking_jobs}</dd>
        </dl>
      )}

      {setMode.isError && (
        <p className="mt-3 text-xs text-rose-500">Failed to change mode — backend may be unreachable.</p>
      )}
    </GlassPanel>
  );
};

export default ComputeControl;
