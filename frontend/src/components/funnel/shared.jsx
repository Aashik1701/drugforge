import React from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * Every place a Vina number appears carries this. A docking score is a
 * ranking signal, NOT a measured binding affinity -- see the constraint in
 * the funnel research (backend/app/funnel/CHANGELOG.md).
 */
export function ScoreDisclaimer({ className = '' }) {
  return (
    <p className={`flex items-start gap-1.5 text-[11px] leading-snug text-gray-500 dark:text-gray-400 ${className}`}>
      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
      <span>
        AutoDock Vina score, kcal/mol. A <strong>computational ranking signal</strong>, not a
        measured binding affinity and not proof of activity. More negative = ranked higher by
        this method.
      </span>
    </p>
  );
}

/** Per-seed docked values as small mono chips; nulls shown as failed seeds. */
export function SeedChips({ perSeed = {} }) {
  const entries = Object.entries(perSeed);
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([seed, v]) => (
        <span
          key={seed}
          title={`seed ${seed}`}
          className={`rounded px-1.5 py-0.5 font-mono text-[10px] tabular-nums ${
            v == null
              ? 'bg-rose-500/15 text-rose-500 line-through'
              : 'bg-gray-500/10 text-gray-600 dark:text-gray-300'
          }`}
        >
          {v == null ? 'fail' : v.toFixed(2)}
        </span>
      ))}
    </div>
  );
}

/** mean affinity with its seed stdev -- variance is a real property of the
 *  method and is never hidden. */
export function AffinityCell({ mean, stdev }) {
  if (mean == null) {
    return <span className="font-mono text-sm text-rose-500">dock failed</span>;
  }
  return (
    <span className="font-mono text-sm tabular-nums text-gray-800 dark:text-gray-100">
      {mean > 0 ? '+' : ''}
      {mean.toFixed(3)}
      {stdev != null && (
        <span className="ml-1 text-xs text-gray-400">± {stdev.toFixed(3)}</span>
      )}
    </span>
  );
}
