import React, { useMemo, useState } from 'react';
import { Play, Database, ClipboardList, AlertTriangle, Zap, Loader2 } from 'lucide-react';
import GlassCard, { GlassButton, GlassBadge } from '../ui/GlassCard';
import FrontierChart from './FrontierChart';
import { useFunnelFrontier } from '../../hooks/useFunnel';
import { useComputePolicy, useSetComputeMode } from '../../hooks/useComputePolicy';
import {
  MAX_UPLOAD, RECOMMENDED_N, clampBudget, parseSmilesInput,
  estWallClockSeconds, formatDuration,
} from '../../utils/funnelState';

function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex rounded-xl border border-white/20 bg-white/5 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            value === o.value
              ? 'bg-teal-500/20 text-teal-700 dark:text-teal-300'
              : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-200'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function FunnelSetup({ sets, isSetsLoading, onStart, isStarting, startError }) {
  const [source, setSource] = useState('set'); // 'set' | 'paste'
  const [setId, setSetId] = useState(null);
  const [smilesText, setSmilesText] = useState('');
  const [target, setTarget] = useState('cox2');
  const [budgetN, setBudgetN] = useState(RECOMMENDED_N);

  const { data: policy } = useComputePolicy();
  const setMode = useSetComputeMode();
  const dockingDisabled =
    policy?.allow_docking === false || startError?.kind === 'docking-disabled';

  const selectedSet = sets?.find((s) => s.set_id === setId) || null;
  const uploadLines = useMemo(() => parseSmilesInput(smilesText), [smilesText]);
  const setSize = source === 'set' ? (selectedSet?.size ?? 45) : uploadLines.length || 45;

  const frontierQ = useFunnelFrontier(source === 'set' ? setId : null);
  const effectiveN = clampBudget(budgetN, setSize);
  const jobs = effectiveN * 4;
  const est = formatDuration(estWallClockSeconds(effectiveN));

  const canStart =
    !isStarting &&
    !dockingDisabled &&
    ((source === 'set' && !!setId) ||
      (source === 'paste' && uploadLines.length > 0 && uploadLines.length <= MAX_UPLOAD));

  const submit = () => {
    const body = { target, budget_n: effectiveN, policy_id: 'v7_binding_weak_cox2' };
    if (source === 'set') body.candidate_set_id = setId;
    else body.smiles = uploadLines;
    onStart(body);
  };

  return (
    <div className="space-y-5">
      {dockingDisabled && (
        <GlassCard hoverable={false} className="border-amber-500/30 bg-amber-500/10 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <div className="text-sm text-amber-700 dark:text-amber-300">
              <p className="font-medium">Docking is disabled in the current compute mode.</p>
              <p className="mt-1 text-amber-600/90 dark:text-amber-400/90">
                The funnel docks the top N candidates, so it needs docking enabled. Switch to
                Balanced mode (the same control on the Dashboard).
              </p>
              <GlassButton
                variant="primary"
                className="mt-3 !px-4 !py-2 text-xs"
                disabled={setMode.isPending}
                onClick={() => setMode.mutate('balanced')}
              >
                <span className="flex items-center gap-2">
                  {setMode.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
                  Enable docking (switch to Balanced)
                </span>
              </GlassButton>
            </div>
          </div>
        </GlassCard>
      )}

      <GlassCard hoverable={false} className="p-6">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
          1 · Candidates
        </h3>
        <Segmented
          value={source}
          onChange={setSource}
          options={[
            { value: 'set', label: 'Committed set' },
            { value: 'paste', label: 'Paste SMILES' },
          ]}
        />

        {source === 'set' && (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {isSetsLoading && <p className="text-sm text-gray-500">Loading sets…</p>}
            {sets?.map((s) => (
              <button
                key={s.set_id}
                type="button"
                onClick={() => { setSetId(s.set_id); setBudgetN((n) => clampBudget(n, s.size)); }}
                className={`rounded-xl border px-4 py-3 text-left transition-colors ${
                  setId === s.set_id
                    ? 'border-teal-500/40 bg-teal-500/10'
                    : 'border-white/15 bg-white/5 hover:bg-white/10'
                }`}
              >
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-gray-400" />
                  <span className="font-mono text-sm text-gray-800 dark:text-gray-100">{s.set_id}</span>
                </div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {s.size} molecules · {s.n_reference} reference
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-gray-400" title={s.content_sha256}>
                  sha256 {s.content_sha256.slice(0, 24)}…
                </div>
              </button>
            ))}
          </div>
        )}

        {source === 'paste' && (
          <div className="mt-4">
            <textarea
              value={smilesText}
              onChange={(e) => setSmilesText(e.target.value)}
              rows={6}
              spellCheck={false}
              placeholder={'One SMILES per line, e.g.\nCC(=O)Oc1ccccc1C(=O)O\nc1ccncc1'}
              className="w-full rounded-xl border border-white/20 bg-white/30 px-4 py-3 font-mono text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:bg-black/30 dark:text-gray-100"
            />
            <div className="mt-1 flex items-center justify-between text-xs">
              <span className={uploadLines.length > MAX_UPLOAD ? 'text-rose-500' : 'text-gray-400'}>
                {uploadLines.length} / {MAX_UPLOAD} molecules
              </span>
              {uploadLines.length > MAX_UPLOAD && <span className="text-rose-500">over the cap</span>}
            </div>

            {startError?.kind === 'parse-failures' && (
              <div className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs">
                <p className="font-medium text-rose-600 dark:text-rose-300">
                  {startError.message}. Fix these and resubmit — nothing was started.
                </p>
                <ul className="mt-2 space-y-1">
                  {startError.parseFailures.map((f) => (
                    <li key={f.index} className="flex gap-2 font-mono text-rose-500">
                      <span className="shrink-0 text-rose-400">line {f.index + 1}:</span>
                      <span className="truncate">{f.smiles}</span>
                      <span className="ml-auto shrink-0 text-rose-400">{f.error}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </GlassCard>

      <GlassCard hoverable={false} className="p-6">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
          2 · Target
        </h3>
        <Segmented
          value={target}
          onChange={setTarget}
          options={[
            { value: 'cox2', label: 'COX-2' },
            { value: 'ace2', label: 'ACE2' },
          ]}
        />
        <p className="mt-2 text-xs text-gray-400">
          The docking receptor. The cheap prescreen is the same either way (frozen v7 policy).
        </p>
      </GlassCard>

      <GlassCard hoverable={false} className="p-6">
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
            3 · Docking budget N
          </h3>
          <span className="font-mono text-sm text-gray-700 dark:text-gray-200">
            N = {effectiveN}
          </span>
        </div>
        <p className="mb-4 text-xs text-gray-400">
          How many prescreen survivors get docked (4 Vina seeds each). See where the trade-off sits:
        </p>

        {source === 'set' && (
          <FrontierChart
            rows={frontierQ.data?.rows ?? (frontierQ.isLoading ? [] : null)}
            selectedN={effectiveN}
            onSelectN={(n) => setBudgetN(n)}
            recommendedN={RECOMMENDED_N}
            setSize={setSize}
          />
        )}
        {source === 'paste' && (
          <p className="rounded-xl border border-white/15 bg-white/5 p-3 text-xs text-gray-400">
            No frontier curve for an ad-hoc list — there is no cached baseline to compare against.
          </p>
        )}

        <input
          type="range"
          min={1}
          max={Math.min(50, setSize)}
          value={effectiveN}
          onChange={(e) => setBudgetN(Number(e.target.value))}
          className="mt-4 w-full accent-teal-500"
          aria-label="Docking budget N"
        />
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <span><strong className="text-gray-700 dark:text-gray-200">{jobs}</strong> Vina jobs</span>
          <span>estimated <strong className="text-gray-700 dark:text-gray-200">{est}</strong> of docking (serial)</span>
          {effectiveN >= 8 && (
            <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-3 w-3" />
              at N={RECOMMENDED_N} this takes roughly 23 minutes; N={setSize} is about 2 hours
            </span>
          )}
        </div>
      </GlassCard>

      <div className="flex items-center gap-3">
        <GlassButton variant="primary" onClick={submit} disabled={!canStart} className="!px-8">
          <span className="flex items-center gap-2">
            {isStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {isStarting ? 'Starting…' : `Run funnel — dock top ${effectiveN}`}
          </span>
        </GlassButton>
        {startError && !['parse-failures', 'docking-disabled', 'already-active'].includes(startError.kind) && (
          <span className="text-sm text-rose-500">{startError.message}</span>
        )}
        <GlassBadge className="ml-auto">policy: v7_binding_weak_cox2 (frozen)</GlassBadge>
      </div>
    </div>
  );
}
