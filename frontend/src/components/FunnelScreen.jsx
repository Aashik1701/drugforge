import React from 'react';
import { motion } from 'framer-motion';
import { GitBranch, Loader2 } from 'lucide-react';
import { useFunnel, useFunnelSets, useFunnelFrontier } from '../hooks/useFunnel';
import FunnelSetup from './funnel/FunnelSetup';
import FunnelRunning from './funnel/FunnelRunning';
import FunnelDone from './funnel/FunnelDone';

/**
 * /app/funnel — the computational funnel as a screen.
 *
 * SETUP    pick candidates + target + N (with the frontier trade-off curve)
 * RUNNING  the narrowing live, docking progress, partial results; safe to leave
 * DONE     ranked shortlist (ties as ties), filtered-out + why, provenance
 *
 * Resumability: useFunnel keeps the active run_id in localStorage and, on
 * mount, GET /api/funnel/status/{id} to reattach. Polling pauses while the tab
 * is hidden (TanStack refetchIntervalInBackground:false) and resumes on focus.
 */
export default function FunnelScreen() {
  const f = useFunnel();
  const setsQ = useFunnelSets();
  // the finished run's set, for the "budget in context" frontier on the DONE view
  const doneFrontierQ = useFunnelFrontier(
    f.view === 'done' ? f.status?.candidate_set_id : null
  );

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 md:px-0 md:pl-24 lg:pl-0">
      <header className="mb-6">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-gradient-to-br from-teal-400/20 to-violet-400/20 p-2.5">
            <GitBranch className="h-5 w-5 text-teal-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Computational funnel</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Cheap prescreen narrows the set; only the top N get docked. One run at a time.
            </p>
          </div>
        </div>
      </header>

      {f.view === 'reattaching' && (
        <div className="flex items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/5 py-16 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Reattaching to your active run…
        </div>
      )}

      {f.view === 'setup' && (
        <>
          {f.viewMeta?.transientError && (
            <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
              Couldn't reach the last run just now — showing setup. If a run is still going it will
              reappear on the next successful check.
            </p>
          )}
          <FunnelSetup
            sets={setsQ.data}
            isSetsLoading={setsQ.isLoading}
            onStart={f.start}
            isStarting={f.isStarting}
            startError={f.startError}
          />
          {f.startError?.kind === 'already-active' && !f.runId && (
            <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              A funnel run is already active on the server, but this browser has no reference to it
              (it may have been started elsewhere). Wait for it to finish, or reload once it's done.
            </p>
          )}
        </>
      )}

      {f.view === 'running' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <FunnelRunning
            status={f.status}
            onCancel={f.cancel}
            isCancelling={f.isCancelling}
            optimistic={f.viewMeta?.optimistic}
          />
        </motion.div>
      )}

      {f.view === 'done' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <FunnelDone
            status={f.status}
            result={f.result}
            frontier={doneFrontierQ.data}
            onReset={f.clear}
          />
          {f.isResultLoading && (
            <p className="mt-3 text-center text-xs text-gray-400">Loading the full run record…</p>
          )}
        </motion.div>
      )}
    </div>
  );
}
