import React from 'react';
import { motion } from 'framer-motion';
import { Loader2, XCircle, Clock, Layers } from 'lucide-react';
import GlassCard, { GlassButton } from '../ui/GlassCard';
import NarrowingViz from './NarrowingViz';
import { AffinityCell, ScoreDisclaimer } from './shared';
import { formatDuration } from '../../utils/funnelState';

const STAGE_COPY = {
  queued: 'Queued — waiting for a compute slot',
  screening: 'Screening — running the cheap filters on every candidate',
  prescreen: 'Ranking survivors — selecting the top N to dock',
  docking: 'Docking — AutoDock Vina, one candidate at a time (serial by design)',
  ranking: 'Ranking docked candidates',
};

export default function FunnelRunning({ status, onCancel, isCancelling, optimistic }) {
  const s = status || {};
  const stage = s.stage || 'queued';
  const docksTotal = s.docks_total || (s.budget_n ? s.budget_n * 4 : 0);
  const docksDone = s.docks_completed || 0;
  const docksFailed = s.docks_failed || 0;
  const submitted = s.docks_submitted || 0;
  const inFlight = s.current_dock_job_id;
  const elapsed = s.elapsed_s;
  const remaining = docksTotal && stage === 'docking'
    ? formatDuration((docksTotal - docksDone - docksFailed) * 35)
    : null;

  const currentMol =
    inFlight && s.prescreen_selected?.length
      ? s.prescreen_selected[Math.min(s.prescreen_selected.length - 1, Math.floor((submitted - 1) / 4))]
      : null;
  const currentSeedIdx = inFlight ? ((submitted - 1) % 4) + 1 : null;

  return (
    <div className="space-y-5">
      <GlassCard hoverable={false} className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
              <Loader2 className="h-4 w-4 animate-spin text-teal-500" />
              {STAGE_COPY[stage] || stage}
            </div>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {s.candidate_set_id} · target {s.target} · N={s.budget_n} · policy {s.policy_id}
              {elapsed != null && <> · <Clock className="inline h-3 w-3" /> {formatDuration(elapsed)} elapsed</>}
            </p>
          </div>
          <GlassButton variant="danger" onClick={onCancel} disabled={isCancelling}>
            <span className="flex items-center gap-2">
              <XCircle className="h-4 w-4" />
              {isCancelling ? 'Cancelling…' : 'Cancel run'}
            </span>
          </GlassButton>
        </div>

        {/* You can close this tab. The run keeps going on the server; polling
            pauses while the tab is hidden and resumes when you return. */}
        <p className="mt-3 rounded-lg bg-teal-500/10 px-3 py-2 text-[11px] text-teal-700 dark:text-teal-300">
          Safe to close this tab — the run continues on the server. This page reattaches to it
          automatically when you come back.
        </p>
      </GlassCard>

      <GlassCard hoverable={false} className="p-6">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
          <Layers className="h-4 w-4" /> The narrowing
        </h3>
        <NarrowingViz
          candidatesIn={s.candidates_in || 0}
          stageSurvivors={s.stage_survivors || []}
          budgetN={s.budget_n}
          docked={stage === 'done' ? s.budget_n : (s.prescreen_selected?.length || undefined)}
        />
      </GlassCard>

      {(stage === 'docking' || stage === 'ranking') && (
        <GlassCard hoverable={false} className="p-6">
          <div className="mb-3 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
              Docking progress
            </h3>
            <span className="font-mono text-sm text-gray-700 dark:text-gray-200 tabular-nums">
              {docksDone}
              {docksFailed > 0 && <span className="text-rose-500"> (+{docksFailed} failed)</span>}
              {' / '}{docksTotal} docks
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-gray-200/60 dark:bg-gray-700/50">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-teal-400 to-violet-400"
              animate={{ width: `${docksTotal ? ((docksDone + docksFailed) / docksTotal) * 100 : 0}%` }}
              transition={{ duration: 0.4 }}
            />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 text-xs text-gray-500 dark:text-gray-400">
            {inFlight ? (
              <span>
                In flight: <span className="font-mono text-gray-700 dark:text-gray-200">{currentMol || '…'}</span>
                {currentSeedIdx && <> · seed {currentSeedIdx} of 4</>}
              </span>
            ) : (
              <span>Between docks…</span>
            )}
            {remaining && <span className="ml-auto">≈ {remaining} remaining (rough)</span>}
          </div>
        </GlassCard>
      )}

      {s.partial_results?.length > 0 && (
        <GlassCard hoverable={false} className="p-6">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
            Results so far
          </h3>
          <div className="space-y-2">
            {[...s.partial_results]
              .sort((a, b) => (a.mean_affinity ?? 99) - (b.mean_affinity ?? 99))
              .map((p) => (
                <div
                  key={p.ligand_id}
                  className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-sm"
                >
                  <span className="font-mono text-gray-700 dark:text-gray-200">{p.ligand_id}</span>
                  <span className="flex items-center gap-3">
                    <span className="text-[11px] text-gray-400">{p.seeds_done}/4 seeds</span>
                    <AffinityCell mean={p.mean_affinity} />
                  </span>
                </div>
              ))}
          </div>
          <ScoreDisclaimer className="mt-3" />
        </GlassCard>
      )}
    </div>
  );
}
