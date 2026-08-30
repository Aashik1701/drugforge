import { test, expect } from '@playwright/test';

/**
 * Funnel screen, end to end against a MOCKED API:
 *   setup -> pick set + N -> start -> RUNNING (narrowing + docking poll)
 *   -> mid-run page refresh reattaches (resumability) -> DONE (ranked shortlist).
 */

const SETS = [
  { set_id: 'cox2_v1', size: 45, n_reference: 11, content_sha256: 'a'.repeat(64), csv: 'app/funnel/datasets/cox2_candidates_v1.csv' },
];
const FRONTIER = {
  set_id: 'cox2_v1',
  rows: [
    { N: 2, docked: 2, jobs: 8, recall5_literal: 0, recall5_tiecredit: 0, recall10_literal: 1, recall10_tiecredit: 1, est_dock_wall_s: 275, speedup_vs_full: 26 },
    { N: 10, docked: 10, jobs: 40, recall5_literal: 2, recall5_tiecredit: 4, recall10_literal: 5, recall10_tiecredit: 9, est_dock_wall_s: 1776, speedup_vs_full: 4 },
    { N: 32, docked: 32, jobs: 128, recall5_literal: 5, recall5_tiecredit: 5, recall10_literal: 9, recall10_tiecredit: 10, est_dock_wall_s: 4320, speedup_vs_full: 1.7 },
  ],
};
const START = {
  run_id: 'funnel_e2e', status: 'queued', candidate_set_id: 'cox2_v1', target: 'cox2',
  budget_n: 2, policy_id: 'v7_binding_weak_cox2', candidates_in: 45,
  message: 'funnel run queued (dock top 2 of 45, 4 seeds each)',
};
const STATUS_SEQUENCE = [
  { run_id: 'funnel_e2e', status: 'running', stage: 'screening', candidate_set_id: 'cox2_v1', target: 'cox2', budget_n: 2, policy_id: 'v7_binding_weak_cox2', candidates_in: 45, stage_survivors: [{ stage: 'smiles_validation', in: 45, out: 45 }], prescreen_selected: [], docks_submitted: 0, docks_total: 8, docks_completed: 0, docks_failed: 0, partial_results: [], elapsed_s: 3 },
  { run_id: 'funnel_e2e', status: 'running', stage: 'docking', candidate_set_id: 'cox2_v1', target: 'cox2', budget_n: 2, policy_id: 'v7_binding_weak_cox2', candidates_in: 45, stage_survivors: [{ stage: 'smiles_validation', in: 45, out: 45 }, { stage: 'druglikeness_filter', in: 45, out: 41 }, { stage: 'toxicity_filter', in: 41, out: 41 }], prescreen_selected: ['CHEMBL111518', 'CHEMBL408215'], docks_submitted: 3, docks_total: 8, docks_completed: 2, docks_failed: 0, current_dock_job_id: 'funnel_e2e__c0s2024', partial_results: [], elapsed_s: 60 },
  // repeated until the test advances it:
  { run_id: 'funnel_e2e', status: 'running', stage: 'docking', candidate_set_id: 'cox2_v1', target: 'cox2', budget_n: 2, policy_id: 'v7_binding_weak_cox2', candidates_in: 45, stage_survivors: [{ stage: 'smiles_validation', in: 45, out: 45 }, { stage: 'druglikeness_filter', in: 45, out: 41 }, { stage: 'toxicity_filter', in: 41, out: 41 }], prescreen_selected: ['CHEMBL111518', 'CHEMBL408215'], docks_submitted: 6, docks_total: 8, docks_completed: 5, docks_failed: 0, current_dock_job_id: 'funnel_e2e__c1s2024', partial_results: [{ ligand_id: 'CHEMBL111518', seeds_done: 4, mean_affinity: -6.41 }], elapsed_s: 200 },
];
const DONE_STATUS = { run_id: 'funnel_e2e', status: 'completed', stage: 'done', candidate_set_id: 'cox2_v1', target: 'cox2', budget_n: 2, policy_id: 'v7_binding_weak_cox2', candidates_in: 45, stage_survivors: [{ stage: 'smiles_validation', in: 45, out: 45 }, { stage: 'druglikeness_filter', in: 45, out: 41 }, { stage: 'toxicity_filter', in: 41, out: 41 }], prescreen_selected: ['CHEMBL111518', 'CHEMBL408215'], docks_submitted: 8, docks_total: 8, docks_completed: 8, docks_failed: 0, current_dock_job_id: null, partial_results: [{ ligand_id: 'CHEMBL111518', seeds_done: 4, mean_affinity: -6.41 }, { ligand_id: 'CHEMBL408215', seeds_done: 4, mean_affinity: -5.85 }], elapsed_s: 280 };
const RESULT = {
  run_id: 'funnel_e2e', path_name: 'funnel', schema_version: '1.0.0',
  platform: 'macOS-26.5.2-arm64-arm-64bit', vina_version: '1.2.7',
  candidate_set_id: 'cox2_v1', candidate_set_size: 45,
  total_docking_jobs_submitted: 8, total_docking_wall_s: 271.4, total_run_wall_s: 277.5,
  docking_params: { exhaustiveness: 8, seeds: [1, 42, 2024, 31337], cpu: 1, target: 'cox2', num_modes: 5, conformer_seed: 42 },
  stage_survivors: [
    { stage: 'smiles_validation', survivors_in: 45, survivors_out: 45, note: '' },
    { stage: 'druglikeness_filter', survivors_in: 45, survivors_out: 41, note: '' },
    { stage: 'toxicity_filter', survivors_in: 41, survivors_out: 41, note: '' },
    { stage: 'dock_top_n', survivors_in: 41, survivors_out: 2, note: '8 jobs = 2 x 4 seeds' },
  ],
  results: [
    { rank: 1, ligand_id: 'CHEMBL111518', smiles: 'NS(=O)(=O)c1ccc', mean_affinity: -6.4115, seed_stdev: 0.2174, per_seed_affinities: { 1: -6.197, 42: -6.61, 2024: -6.647, 31337: -6.192 }, dock_wall_s: 140, tie_group: null },
    { rank: 2, ligand_id: 'CHEMBL408215', smiles: 'NS(=O)(=O)c1ccc', mean_affinity: -5.851, seed_stdev: 0.0362, per_seed_affinities: { 1: -5.789, 42: -5.868, 2024: -5.867, 31337: -5.88 }, dock_wall_s: 130, tie_group: 'tie1' },
    { rank: 3, ligand_id: 'CHEMBL411894', smiles: 'NS(=O)(=O)c1ccc', mean_affinity: -5.7315, seed_stdev: 0.1347, per_seed_affinities: { 1: -5.588, 42: -5.606, 2024: -5.87, 31337: -5.862 }, dock_wall_s: 120, tie_group: 'tie1' },
  ],
  filtered_out: [
    { ligand_id: 'CHEMBL67659', smiles: 'CS(=O)', stage: 'druglikeness', reason: 'MolLogP 6.42 outside [-1.0, 6.0]' },
  ],
  funnel_policy: { ranker: 'binding_weak_cox2' },
  per_candidate: null,
  notes: ['candidate_set_sha256=9ae649ec19fe9a206e8bdbd3a2b43609e89623f8d713a511d05c0bd33c7d35af', 'served via POST /api/funnel/start (funnel.service)'],
};

async function mockApi(page, getPhase) {
  await page.route('**/api/compute/policy', (r) =>
    r.fulfill({ json: { mode: 'balanced', allow_docking: true, allow_large_batches: false, allow_parallel_jobs: false, max_local_jobs: 2, max_docking_jobs: 1, max_runtime: 600 } }));
  await page.route('**/api/funnel/sets', (r) => r.fulfill({ json: SETS }));
  await page.route('**/api/funnel/frontier/cox2_v1', (r) => r.fulfill({ json: FRONTIER }));
  await page.route('**/api/funnel/start', (r) => r.fulfill({ json: START }));
  await page.route('**/api/funnel/status/funnel_e2e', (r) => {
    const phase = getPhase();
    if (phase === 'done') return r.fulfill({ json: DONE_STATUS });
    const i = Math.min(phase, STATUS_SEQUENCE.length - 1);
    return r.fulfill({ json: STATUS_SEQUENCE[i] });
  });
  await page.route('**/api/funnel/result/funnel_e2e', (r) => r.fulfill({ json: RESULT }));
}

test('funnel: setup -> start -> running -> refresh reattaches -> done', async ({ page }) => {
  // status polls back off to 5s in the docking stage; this walk crosses several
  // poll boundaries (running -> reload -> running -> done) so give it room.
  test.setTimeout(60_000);
  // mock the localStorage auth the app uses (no real auth backend)
  await page.addInitScript(() => {
    localStorage.setItem('authToken', 'mock-e2e');
    localStorage.setItem('user', JSON.stringify({ id: 'e2e', email: 'e2e@test', name: 'e2e', role: 'user' }));
  });

  let phase = 0; // index into STATUS_SEQUENCE, or the string 'done'
  await mockApi(page, () => phase);

  // ---- SETUP ----
  await page.goto('/app/funnel');
  await expect(page.getByRole('heading', { name: /Computational funnel/i })).toBeVisible();
  await page.getByRole('button', { name: /cox2_v1/ }).click();
  await expect(page.getByText(/recommended/i)).toBeVisible(); // frontier rendered
  await page.locator('input[type="range"]').fill('2');
  await expect(page.getByText('8 Vina jobs')).toBeVisible();

  // ---- START -> RUNNING ----
  await page.getByRole('button', { name: /Run funnel — dock top 2/ }).click();
  await expect(page.getByText(/The narrowing/i)).toBeVisible();
  await expect(page.getByRole('button', { name: /Cancel run/i })).toBeVisible();

  // advance the mock to the docking phase and let a poll land
  phase = 1;
  await expect(page.getByText(/Docking progress/i)).toBeVisible();
  await expect(page.getByText('2 / 8 docks')).toBeVisible();
  await expect(page.getByText('CHEMBL111518', { exact: false })).toBeVisible();
  // narrowing counts arrived: 45 -> 45 -> 41 -> 41
  await expect(page.getByText('-4')).toBeVisible(); // drug-likeness dropped 4

  // ---- MID-RUN REFRESH: must reattach, not fall back to setup ----
  phase = 2;
  await page.reload();
  await expect(page.getByRole('button', { name: /Cancel run/i })).toBeVisible();
  await expect(page.getByText(/Docking progress/i)).toBeVisible();
  await expect(page.getByText('5 / 8 docks')).toBeVisible();
  await expect(page.getByRole('button', { name: /Run funnel/ })).toHaveCount(0); // NOT setup

  // ---- DONE ----
  phase = 'done';
  await expect(page.getByText(/Run complete/i)).toBeVisible();
  await expect(page.getByRole('heading', { name: /Ranked shortlist/i })).toBeVisible();
  await expect(page.getByText('CHEMBL111518')).toBeVisible();
  // tie group rendered AS a tie
  await expect(page.getByText(/tie · 2 candidates/i)).toBeVisible();
  // seed stdev is visible (variance not hidden)
  await expect(page.getByText(/± 0.217/)).toBeVisible();
  // filtered-out reason with its threshold
  await expect(page.getByText(/MolLogP 6.42 outside/)).toBeVisible();
  // provenance
  await expect(page.getByText('1.2.7')).toBeVisible();
  await expect(page.getByText(/9ae649ec19fe/)).toBeVisible();
  // never call a Vina score a measured binding affinity
  await expect(page.getByText(/ranking signal/i).first()).toBeVisible();
});

test('funnel: docking disabled offers the compute-mode switch, not a raw 503', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('authToken', 'mock-e2e');
    localStorage.setItem('user', JSON.stringify({ id: 'e2e', email: 'e2e@test', name: 'e2e', role: 'user' }));
  });
  await page.route('**/api/compute/policy', (r) =>
    r.fulfill({ json: { mode: 'battery-saver', allow_docking: false, allow_large_batches: false, allow_parallel_jobs: false, max_local_jobs: 1, max_docking_jobs: 0, max_runtime: 600 } }));
  await page.route('**/api/funnel/sets', (r) => r.fulfill({ json: SETS }));
  await page.route('**/api/funnel/frontier/cox2_v1', (r) => r.fulfill({ json: FRONTIER }));
  await page.route('**/api/funnel/status/**', (r) => r.fulfill({ status: 404, json: { error: 'no funnel run' } }));

  await page.goto('/app/funnel');
  await expect(page.getByText(/Docking is disabled in the current compute mode/i)).toBeVisible();
  await expect(page.getByRole('button', { name: /Enable docking \(switch to Balanced\)/i })).toBeVisible();
});
