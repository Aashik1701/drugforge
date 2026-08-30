import { describe, it, expect } from 'vitest';
import {
  deriveView,
  pollInterval,
  groupResults,
  isFailedDock,
  failedSeeds,
  parseStartError,
  estWallClockSeconds,
  formatDuration,
  clampBudget,
  parseSmilesInput,
  shaFromNotes,
  TIE_EPSILON,
} from './funnelState';

describe('deriveView - the SETUP / RUNNING / DONE state machine', () => {
  it('shows setup with no run pointer', () => {
    expect(deriveView({ runId: null }).view).toBe('setup');
  });

  it('shows running optimistically while a start request is in flight', () => {
    expect(deriveView({ runId: null, starting: true })).toEqual({ view: 'running', optimistic: true });
  });

  it('reattaches: pointer present, first status fetch still pending', () => {
    expect(deriveView({ runId: 'funnel_abc', statusFetching: true }).view).toBe('reattaching');
  });

  it('running once status says queued or running', () => {
    expect(deriveView({ runId: 'funnel_abc', statusData: { status: 'queued', stage: 'queued' } }).view).toBe('running');
    expect(deriveView({ runId: 'funnel_abc', statusData: { status: 'running', stage: 'docking' } }).view).toBe('running');
  });

  it('done for every terminal status', () => {
    for (const s of ['completed', 'failed', 'cancelled']) {
      expect(deriveView({ runId: 'funnel_abc', statusData: { status: s } }).view).toBe('done');
    }
  });

  it('a stale pointer (404) drops back to setup and asks to clear the pointer', () => {
    const r = deriveView({ runId: 'funnel_dead', statusError: { status: 404 } });
    expect(r).toEqual({ view: 'setup', clearPointer: true });
    const r2 = deriveView({ runId: 'funnel_dead', statusError: { response: { status: 404 } } });
    expect(r2.clearPointer).toBe(true);
  });

  it('a transient non-404 error with no data keeps the pointer', () => {
    const r = deriveView({ runId: 'funnel_abc', statusError: { status: 500 }, statusFetching: false });
    expect(r).toEqual({ view: 'setup', clearPointer: false, transientError: true });
  });
});

describe('pollInterval - cadence by stage', () => {
  it('polls fast during the short local stages', () => {
    expect(pollInterval({ status: 'running', stage: 'screening' })).toBe(2000);
    expect(pollInterval({ status: 'queued', stage: 'queued' })).toBe(2000);
  });
  it('backs off to 5s once docking starts (a dock takes ~20-160s)', () => {
    expect(pollInterval({ status: 'running', stage: 'docking' })).toBe(5000);
    expect(pollInterval({ status: 'running', stage: 'ranking' })).toBe(5000);
  });
  it('stops polling on a terminal status', () => {
    expect(pollInterval({ status: 'completed', stage: 'done' })).toBe(false);
    expect(pollInterval({ status: 'cancelled', stage: 'cancelled' })).toBe(false);
  });
});

describe('groupResults - ties are shown as ties, not false-precision ranks', () => {
  it('folds consecutive entries sharing a tie_group into one group', () => {
    const results = [
      { rank: 1, ligand_id: 'A', tie_group: null },
      { rank: 2, ligand_id: 'B', tie_group: 'tie1' },
      { rank: 3, ligand_id: 'C', tie_group: 'tie1' },
      { rank: 4, ligand_id: 'D', tie_group: 'tie2' },
      { rank: 5, ligand_id: 'E', tie_group: 'tie2' },
      { rank: 6, ligand_id: 'F', tie_group: null },
    ];
    const groups = groupResults(results);
    expect(groups).toHaveLength(4);
    expect(groups[0]).toMatchObject({ tie: false, members: [{ ligand_id: 'A' }] });
    expect(groups[1]).toMatchObject({ tie: true, tieGroup: 'tie1' });
    expect(groups[1].members.map((m) => m.ligand_id)).toEqual(['B', 'C']);
    expect(groups[2].members.map((m) => m.ligand_id)).toEqual(['D', 'E']);
    expect(groups[3].tie).toBe(false);
  });

  it('a lone member with a tie_group is not rendered as a tie', () => {
    const groups = groupResults([{ rank: 1, ligand_id: 'A', tie_group: 'tie9' }]);
    expect(groups[0].tie).toBe(false);
  });

  it('empty input -> empty output', () => {
    expect(groupResults()).toEqual([]);
  });
});

describe('failed-dock detection', () => {
  it('flags an entry where every seed failed', () => {
    expect(isFailedDock({ mean_affinity: null, per_seed_affinities: { 1: null, 42: null } })).toBe(true);
  });
  it('does not flag a fully or partly docked entry', () => {
    expect(isFailedDock({ mean_affinity: -6.1, per_seed_affinities: { 1: -6.1 } })).toBe(false);
    expect(isFailedDock({ mean_affinity: null, per_seed_affinities: { 1: -6.1, 42: null } })).toBe(false);
  });
  it('reports which seeds failed', () => {
    expect(failedSeeds({ per_seed_affinities: { 1: -6.1, 42: null, 2024: null, 31337: -6.0 } }))
      .toEqual(['42', '2024']);
  });
});

describe('parseStartError - honest classification of a failed start', () => {
  it('docking disabled (battery-saver) 503', () => {
    const e = { response: { status: 503, data: { error: 'Docking is disabled in battery-saver mode' } } };
    expect(parseStartError(e)).toMatchObject({ kind: 'docking-disabled' });
  });
  it('another run already active 503', () => {
    const e = { response: { status: 503, data: { error: 'a funnel run is already active; only one at a time' } } };
    expect(parseStartError(e).kind).toBe('already-active');
  });
  it('per-index parse failures from a 400', () => {
    const e = {
      response: {
        status: 400,
        data: {
          error: {
            parse_failures: [
              { index: 1, smiles: 'not a molecule', error: 'RDKit could not parse' },
              { index: 4, smiles: '???', error: 'RDKit could not parse' },
            ],
            n_valid: 3,
          },
        },
      },
    };
    const r = parseStartError(e);
    expect(r.kind).toBe('parse-failures');
    expect(r.parseFailures).toHaveLength(2);
    expect(r.parseFailures[0].index).toBe(1);
    expect(r.nValid).toBe(3);
    expect(r.message).toMatch(/2 of 5/);
  });
  it('a plain 413 budget rejection is a validation error', () => {
    const e = { response: { status: 413, data: { error: 'budget_n must be in [1, 50]; got 1000' } } };
    expect(parseStartError(e).kind).toBe('validation');
  });
  it('a network error with no response is unknown', () => {
    expect(parseStartError({ message: 'Network Error' }).kind).toBe('unknown');
  });
});

describe('wall-clock estimate anchors', () => {
  it('matches the three stated reference points', () => {
    expect(formatDuration(estWallClockSeconds(3))).toMatch(/min|s/);
    expect(estWallClockSeconds(10)).toBe(1400); // ~23 min
    expect(formatDuration(estWallClockSeconds(10))).toBe('about 23 min');
    expect(formatDuration(estWallClockSeconds(45))).toMatch(/about (1\.5|2) h/);
  });
});

describe('small helpers', () => {
  it('clampBudget respects the server cap and the set size', () => {
    expect(clampBudget(1000, 45)).toBe(45);
    expect(clampBudget(30, 45)).toBe(30);
    expect(clampBudget(0, 45)).toBe(1);
    expect(clampBudget(80, 200)).toBe(50); // MAX_BUDGET_N
  });
  it('parseSmilesInput splits on newlines and commas, drops blanks', () => {
    expect(parseSmilesInput('CCO\n\nc1ccccc1 ,  CC(=O)O\n')).toEqual(['CCO', 'c1ccccc1', 'CC(=O)O']);
  });
  it('shaFromNotes pulls the candidate-set hash out of RunRecord.notes', () => {
    expect(shaFromNotes(['candidate_set_sha256=9ae649ec', 'x'])).toBe('9ae649ec');
    expect(shaFromNotes(['nothing here'])).toBeNull();
  });
  it('TIE_EPSILON matches the backend constant', () => {
    expect(TIE_EPSILON).toBe(0.1);
  });
});
