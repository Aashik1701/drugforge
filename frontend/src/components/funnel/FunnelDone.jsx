import React from 'react';
import { CheckCircle2, XCircle, Ban, Filter, FileText, RotateCcw } from 'lucide-react';
import GlassCard, { GlassButton, GlassBadge } from '../ui/GlassCard';
import FrontierChart from './FrontierChart';
import { AffinityCell, SeedChips, ScoreDisclaimer } from './shared';
import { groupResults, isFailedDock, failedSeeds, shaFromNotes, TIE_EPSILON } from '../../utils/funnelState';

function Outcome({ status, error }) {
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-5 w-5" /> Run complete
      </span>
    );
  }
  if (status === 'cancelled') {
    return (
      <span className="flex items-center gap-2 text-gray-500">
        <Ban className="h-5 w-5" /> Run cancelled — partial results below
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
      <XCircle className="h-5 w-5" /> Run failed{error ? ` — ${error}` : ''}
    </span>
  );
}

export default function FunnelDone({ status, result, frontier, onReset }) {
  const s = status || {};
  const rec = result; // full RunRecord v1.0.0, or undefined if failed/cancelled before completion
  const results = rec?.results || [];
  const groups = groupResults(results);
  const filteredOut = rec?.filtered_out || [];
  const dp = rec?.docking_params || {};
  const sha = shaFromNotes(rec?.notes);
  const failedList = results.filter(isFailedDock);

  return (
    <div className="space-y-5">
      <GlassCard hoverable={false} className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-base font-semibold">
            <Outcome status={s.status} error={s.error} />
          </div>
          <GlassButton variant="ghost" onClick={onReset}>
            <span className="flex items-center gap-2"><RotateCcw className="h-4 w-4" /> New run</span>
          </GlassButton>
        </div>
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          {s.candidate_set_id} · target {s.target} · docked top {rec?.stage_survivors?.find((x) => x.stage === 'dock_top_n')?.survivors_out ?? s.budget_n}
          {rec && <> · {rec.total_docking_jobs_submitted} Vina jobs · {Math.round(rec.total_docking_wall_s)}s docking wall-clock</>}
        </p>
      </GlassCard>

      {/* ranked shortlist */}
      <GlassCard hoverable={false} className="p-6">
        <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
          Ranked shortlist
        </h3>
        <p className="mb-4 text-[11px] text-gray-400">
          Ranked on mean best-affinity across {dp.seeds?.length || 4} seeds. Candidates within
          {' '}{TIE_EPSILON} kcal/mol are grouped as a <strong>tie</strong> — this method cannot tell them apart.
        </p>

        {groups.length === 0 && (
          <p className="text-sm text-gray-500">No docked results (the run did not complete a dock).</p>
        )}

        <ol className="space-y-2">
          {groups.map((g) => (
            <li
              key={g.tie ? g.tieGroup : g.members[0].ligand_id}
              className={`rounded-xl border px-4 py-3 ${
                g.tie
                  ? 'border-violet-400/30 bg-violet-500/5'
                  : 'border-white/15 bg-white/5'
              }`}
            >
              <div className="mb-1 flex items-center gap-2">
                <span className="font-mono text-xs text-gray-400">
                  {g.tie ? `#${g.members[0].rank}–${g.members[g.members.length - 1].rank}` : `#${g.members[0].rank}`}
                </span>
                {g.tie && <GlassBadge variant="primary">tie · {g.members.length} candidates</GlassBadge>}
              </div>
              <div className="space-y-2">
                {g.members.map((m) => (
                  <div key={m.ligand_id} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-sm text-gray-800 dark:text-gray-100">
                      {m.ligand_id}
                      {isFailedDock(m) && <GlassBadge variant="danger" className="ml-2">dock failed</GlassBadge>}
                      {!isFailedDock(m) && failedSeeds(m).length > 0 && (
                        <GlassBadge variant="warning" className="ml-2">seeds {failedSeeds(m).join(', ')} failed</GlassBadge>
                      )}
                    </span>
                    <span className="flex items-center gap-3">
                      <SeedChips perSeed={m.per_seed_affinities} />
                      <AffinityCell mean={m.mean_affinity} stdev={m.seed_stdev} />
                    </span>
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ol>
        <ScoreDisclaimer className="mt-4" />
      </GlassCard>

      {/* failed docks called out explicitly */}
      {failedList.length > 0 && (
        <GlassCard hoverable={false} className="p-6">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-rose-500">
            <XCircle className="h-4 w-4" /> {failedList.length} candidate{failedList.length > 1 ? 's' : ''} failed to dock
          </h3>
          <p className="mb-3 text-[11px] text-gray-400">
            The run continues past a failed dock; these are shown so the shortlist isn't silently shorter.
          </p>
          <ul className="space-y-1 text-sm">
            {failedList.map((m) => (
              <li key={m.ligand_id} className="flex justify-between font-mono text-gray-600 dark:text-gray-300">
                <span>{m.ligand_id}</span>
                <span className="text-xs text-rose-400 truncate max-w-[60%]">{m.smiles}</span>
              </li>
            ))}
          </ul>
        </GlassCard>
      )}

      {/* filtered-out molecules + why */}
      {filteredOut.length > 0 && (
        <GlassCard hoverable={false} className="p-6">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
            <Filter className="h-4 w-4" /> Filtered out before docking ({filteredOut.length})
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-gray-400">
                <th className="pb-2">candidate</th><th className="pb-2">stage</th><th className="pb-2">reason (threshold)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredOut.map((f) => (
                <tr key={f.ligand_id}>
                  <td className="py-1.5 font-mono text-gray-700 dark:text-gray-200">{f.ligand_id}</td>
                  <td className="py-1.5"><GlassBadge>{f.stage}</GlassBadge></td>
                  <td className="py-1.5 text-gray-500 dark:text-gray-400">{f.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}

      {/* provenance */}
      {rec && (
        <GlassCard hoverable={false} className="p-6">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
            <FileText className="h-4 w-4" /> Provenance
          </h3>
          <dl className="grid grid-cols-1 gap-x-8 gap-y-1.5 text-xs sm:grid-cols-2">
            {[
              ['candidate set', `${rec.candidate_set_id} (${rec.candidate_set_size} molecules)`],
              ['content sha256', sha],
              ['exhaustiveness', dp.exhaustiveness],
              ['seeds', (dp.seeds || []).join(', ')],
              ['cpu threads', dp.cpu],
              ['conformer seed', dp.conformer_seed],
              ['num poses', dp.num_modes],
              ['AutoDock Vina', rec.vina_version],
              ['platform', rec.platform],
              ['schema', rec.schema_version],
            ].map(([k, v]) => (
              <React.Fragment key={k}>
                <dt className="text-gray-400">{k}</dt>
                <dd className="break-all font-mono text-gray-700 dark:text-gray-200">{v ?? '—'}</dd>
              </React.Fragment>
            ))}
          </dl>
        </GlassCard>
      )}

      {/* the frontier, so the result reads in context of the budget chosen */}
      <GlassCard hoverable={false} className="p-6">
        <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
          Budget in context
        </h3>
        <p className="mb-4 text-[11px] text-gray-400">
          Where the N you docked ({s.budget_n}) sits on the recall-vs-budget curve for this set.
        </p>
        <FrontierChart
          rows={frontier?.rows ?? null}
          selectedN={s.budget_n}
          setSize={rec?.candidate_set_size || 45}
        />
      </GlassCard>
    </div>
  );
}
