/**
 * Pure helpers for the funnel screen: the SETUP / RUNNING / DONE state machine,
 * tie grouping, start-error classification, polling cadence, and the wall-clock
 * estimate. No React, no network -- unit-tested in funnelState.test.js.
 *
 * The funnel run itself lives on the server (a `funnel` Job in the backend
 * JobStore). The frontend only holds a POINTER to it (the run_id) so it can
 * reattach after a reload. See useFunnel.js for where that pointer is stored.
 */

export const TIE_EPSILON = 0.10; // kcal/mol -- from backend funnel/ranking.py
export const RECOMMENDED_N = 10;
export const MAX_UPLOAD = 100; // backend FUNNEL_MAX_UPLOAD
export const MAX_BUDGET_N = 50; // backend FUNNEL_MAX_BUDGET_N
export const SECONDS_PER_DOCK = 35; // reference-machine rough mean; docks vary 10-160s

export const TERMINAL = ['completed', 'failed', 'cancelled'];
export const ACTIVE = ['queued', 'running'];

/**
 * The single source of truth for what the screen shows.
 *  - no run pointer, nothing pending            -> 'setup'
 *  - a start request is in flight               -> 'running' (optimistic)
 *  - have a pointer, first status fetch pending  -> 'reattaching'
 *  - status says queued/running                  -> 'running'
 *  - status says completed/failed/cancelled      -> 'done'
 *  - status 404 (stale pointer)                  -> 'setup' (+ signal to clear it)
 */
export function deriveView({ runId, starting, statusData, statusError, statusFetching }) {
  if (starting) return { view: 'running', optimistic: true };
  if (!runId) return { view: 'setup' };

  const notFound =
    statusError &&
    (statusError.status === 404 || statusError?.response?.status === 404);
  if (notFound) return { view: 'setup', clearPointer: true };

  if (!statusData) {
    // have a pointer but no data yet: reattaching on load, or a transient miss
    return statusFetching || !statusError
      ? { view: 'reattaching' }
      : { view: 'setup', clearPointer: false, transientError: true };
  }

  if (TERMINAL.includes(statusData.status)) return { view: 'done' };
  return { view: 'running' };
}

/** How often to poll, by stage. `false` = stop. Hidden-tab pausing is handled
 *  by TanStack's refetchIntervalInBackground:false, not here. */
export function pollInterval(statusData) {
  if (!statusData) return 2000;
  if (TERMINAL.includes(statusData.status)) return false;
  const stage = statusData.stage;
  if (stage === 'docking' || stage === 'ranking') return 5000;
  return 2000; // queued | screening | prescreen
}

/**
 * Fold a ranked results array into render groups. Consecutive entries that
 * share a non-null `tie_group` (assigned by the backend when they are within
 * TIE_EPSILON) become ONE group and are shown as a tie, never as distinct
 * ranks. Everything else is a singleton.
 */
export function groupResults(results = []) {
  const groups = [];
  for (const entry of results) {
    const last = groups[groups.length - 1];
    if (entry.tie_group && last && last.tie && last.tieGroup === entry.tie_group) {
      last.members.push(entry);
    } else if (entry.tie_group) {
      groups.push({ tie: true, tieGroup: entry.tie_group, rank: entry.rank, members: [entry] });
    } else {
      groups.push({ tie: false, rank: entry.rank, members: [entry] });
    }
  }
  // a "tie group" with a single member is not a tie
  return groups.map((g) =>
    g.tie && g.members.length === 1 ? { ...g, tie: false } : g
  );
}

/** True if this docked entry has no usable affinity at all (every seed failed). */
export function isFailedDock(entry) {
  if (!entry) return false;
  const perSeed = entry.per_seed_affinities || {};
  const anyOk = Object.values(perSeed).some((v) => v != null);
  return entry.mean_affinity == null && !anyOk;
}

/** Which seeds failed for a partially-docked entry. */
export function failedSeeds(entry) {
  const perSeed = entry?.per_seed_affinities || {};
  return Object.entries(perSeed).filter(([, v]) => v == null).map(([s]) => s);
}

/**
 * Classify a POST /api/funnel/start failure. The backend wraps
 * HTTPException.detail under `{"error": ...}` (see backend/app/main.py).
 */
export function parseStartError(err) {
  const resp = err?.response;
  const status = resp?.status;
  const body = resp?.data ?? {};
  const detail = body.error ?? body.detail ?? body;
  const text = typeof detail === 'string' ? detail : (detail?.message || '');

  if (status === 503 && /battery-saver|docking is disabled/i.test(text)) {
    return { kind: 'docking-disabled', message: text };
  }
  if (status === 503 && /already active/i.test(text)) {
    return { kind: 'already-active', message: text };
  }
  if (status === 400 && detail && Array.isArray(detail.parse_failures)) {
    return {
      kind: 'parse-failures',
      message: `${detail.parse_failures.length} of ${detail.parse_failures.length + (detail.n_valid ?? 0)} SMILES could not be parsed`,
      parseFailures: detail.parse_failures,
      nValid: detail.n_valid ?? 0,
    };
  }
  if (status === 400 || status === 413) {
    return { kind: 'validation', message: text || 'The request was rejected by the server.' };
  }
  return {
    kind: 'unknown',
    message: text || err?.message || 'Could not start the funnel run.',
  };
}

/** Rough wall-clock for docking N candidates x 4 seeds, serial. Approximate:
 *  reference machine, docks range 10-160s. N=3->~7min, N=10->~23min, N=45->~2h. */
export function estWallClockSeconds(n) {
  return Math.max(0, Math.round(n)) * 4 * SECONDS_PER_DOCK;
}

export function formatDuration(totalSeconds) {
  if (totalSeconds == null || Number.isNaN(totalSeconds)) return '--';
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 90) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 90) return `about ${m} min`;
  const h = m / 60;
  return h < 1.75 ? `about ${Math.round(h * 2) / 2} h` : `about ${Math.round(h)} h`;
}

/** Clamp a user-picked N to the server bounds and the set size. */
export function clampBudget(n, setSize) {
  const upper = Math.min(MAX_BUDGET_N, setSize || MAX_BUDGET_N);
  return Math.min(upper, Math.max(1, Math.round(n || 1)));
}

/** Split a pasted textarea into SMILES lines, dropping blanks. */
export function parseSmilesInput(text) {
  return (text || '')
    .split(/[\r\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Extract the candidate-set sha256 the backend records in RunRecord.notes[0]. */
export function shaFromNotes(notes = []) {
  const hit = notes.find((n) => typeof n === 'string' && n.startsWith('candidate_set_sha256='));
  return hit ? hit.split('=')[1] : null;
}

export const STAGE_LABELS = {
  smiles_validation: 'SMILES valid',
  druglikeness_filter: 'drug-likeness',
  toxicity_filter: 'toxicity',
  dock_top_n: 'docked',
};

/** Both /status (`{stage,in,out}`) and RunRecord (`{stage,survivors_in,
 *  survivors_out,note}`) describe the funnel stages -- fold to one shape. */
export function normalizeStages(arr = []) {
  return arr.map((s) => ({
    stage: s.stage,
    label: STAGE_LABELS[s.stage] || s.stage,
    in: s.in ?? s.survivors_in ?? 0,
    out: s.out ?? s.survivors_out ?? 0,
    note: s.note || '',
  }));
}
