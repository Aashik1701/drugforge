import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Clock,
  Download,
  FlaskConical,
  History,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Sliders,
  Sparkles,
  StopCircle,
  Target,
  X,
  ChevronDown,
  ChevronUp,
  Zap,
  CheckCircle2,
  XCircle,
  Ban,
} from 'lucide-react';
import { useDocking } from '../hooks/useDocking';
import { dockingService } from '../services/api';
import DockingPoseViewer from './DockingPoseViewer';
import HeavyComputeConfirm from './HeavyComputeConfirm';
import { useComputePolicy } from '../hooks/useComputePolicy';

const TARGET_OPTIONS = [
  { value: 'cox2', label: 'COX-2', desc: 'Cyclooxygenase-2' },
  { value: 'ace2', label: 'ACE2', desc: 'Angiotensin-Converting Enzyme 2' },
];

const EXAMPLE_SMILES = [
  { name: 'Aspirin', smiles: 'CC(=O)OC1=CC=CC=C1C(=O)O' },
  { name: 'Ibuprofen', smiles: 'CC(C)CC1=CC=C(C=C1)C(C)C(=O)O' },
  { name: 'Caffeine', smiles: 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C' },
  { name: 'Paracetamol', smiles: 'CC(=O)NC1=CC=C(O)C=C1' },
  { name: 'Naproxen', smiles: 'COC1=CC2=CC(=CC2=CC1)C(C)C(=O)O' },
  { name: 'Celecoxib', smiles: 'CC1=CC=C(C=C1)C2=CC(=NN2C3=CC=C(C=C3)S(=O)(=O)N)C(F)(F)F' },
];

const STATUS_CONFIG = {
  idle:       { label: 'Ready', color: 'text-slate-400', bg: 'bg-slate-500/10 border-slate-500/20' },
  queued:     { label: 'Queued', color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/30' },
  processing: { label: 'Docking...', color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/30' },
  completed:  { label: 'Completed', color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30' },
  failed:     { label: 'Failed', color: 'text-rose-400', bg: 'bg-rose-500/10 border-rose-500/30' },
  cancelled:  { label: 'Cancelled', color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30' },
};

const STATUS_ICON = {
  queued: <Clock className="w-3.5 h-3.5 animate-pulse" />,
  processing: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
  completed: <CheckCircle2 className="w-3.5 h-3.5" />,
  failed: <XCircle className="w-3.5 h-3.5" />,
  cancelled: <Ban className="w-3.5 h-3.5" />,
};

/* ---------- Elapsed timer hook ---------- */
function useElapsedTimer(running) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    if (running) {
      startRef.current = Date.now();
      const tick = () => {
        setElapsed(((Date.now() - startRef.current) / 1000));
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } else {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    }
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [running]);

  const resetTimer = useCallback(() => setElapsed(0), []);
  return { elapsed, resetTimer };
}

/* ---------- Download helpers ---------- */
function downloadFile(content, filename, mime = 'chemical/x-pdbqt') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadJSON(obj, filename) {
  downloadFile(JSON.stringify(obj, null, 2), filename, 'application/json');
}

/* ========== DockingStudio Component ========== */
const DockingStudio = () => {
  /* --- Form state --- */
  const [smiles, setSmiles] = useState('CC(=O)OC1=CC=CC=C1C(=O)O');
  const [target, setTarget] = useState('cox2');
  const [exhaustiveness, setExhaustiveness] = useState(8);
  const [showAdvanced, setShowAdvanced] = useState(false);

  /* --- Receptor --- */
  const [receptorPdbqt, setReceptorPdbqt] = useState('');
  const [receptorInfo, setReceptorInfo] = useState(null);
  const [receptorError, setReceptorError] = useState('');

  /* --- History --- */
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  /* --- Docking hook --- */
  const {
    taskId,
    status,
    result,
    error,
    isSubmitting,
    isCancelling,
    isProcessing,
    startDocking,
    cancelDocking,
    reset,
  } = useDocking();

  /* --- Elapsed timer --- */
  const { elapsed, resetTimer } = useElapsedTimer(isProcessing);

  const canRun = useMemo(
    () => smiles.trim().length > 0 && !isProcessing && !isSubmitting,
    [smiles, isProcessing, isSubmitting],
  );

  const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  /* --- Receptor loader --- */
  const loadReceptor = useCallback(async (selectedTarget) => {
    try {
      setReceptorError('');
      const response = await dockingService.getReceptor(selectedTarget);
      setReceptorPdbqt(response.data?.receptor_pdbqt || '');
      setReceptorInfo(response.data || null);
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || 'Failed to load receptor';
      setReceptorError(message);
      setReceptorPdbqt('');
      setReceptorInfo(null);
    }
  }, []);

  useEffect(() => { loadReceptor(target); }, [target, loadReceptor]);

  /* --- History loader --- */
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await dockingService.getHistory();
      setHistory(res.data || []);
    } catch { /* ignore */ }
    finally { setHistoryLoading(false); }
  }, []);

  // Refresh history when a task finishes
  useEffect(() => {
    if (status === 'completed' || status === 'failed' || status === 'cancelled') {
      loadHistory();
    }
  }, [status, loadHistory]);

  /* --- Handlers --- */
  const [showConfirm, setShowConfirm] = useState(false);
  const { data: computePolicy } = useComputePolicy();

  const handleRun = (e) => {
    e.preventDefault();
    if (!canRun) return;
    setShowConfirm(true);
  };

  const handleConfirmedRun = async () => {
    setShowConfirm(false);
    resetTimer();
    await startDocking({ smiles: smiles.trim(), target, exhaustiveness });
  };

  const handleCancel = async () => {
    await cancelDocking();
  };

  const handleReset = () => {
    reset();
    resetTimer();
  };

  const handleExampleClick = (exSmiles) => {
    setSmiles(exSmiles);
  };

  const handleHistoryReplay = (entry) => {
    setSmiles(entry.smiles);
    setTarget(entry.target);
    if (entry.exhaustiveness) setExhaustiveness(entry.exhaustiveness);
    setShowHistory(false);
  };

  const handleDownloadPose = () => {
    if (result?.docked_ligand_pdbqt) {
      downloadFile(result.docked_ligand_pdbqt, `docked_${target}_${taskId}.pdbqt`);
    }
  };

  const handleDownloadSummary = () => {
    if (!result) return;
    const summary = {
      task_id: taskId,
      smiles,
      target,
      exhaustiveness,
      affinity_kcal_mol: result.affinity_kcal_mol,
      mode: result.mode,
      receptor: result.receptor_pdbqt,
      elapsed_seconds: result.elapsed_seconds,
      started_at: result.started_at,
      finished_at: result.finished_at,
    };
    downloadJSON(summary, `docking_summary_${taskId}.json`);
  };

  /* --- Render --- */
  return (
    <div className="h-full flex flex-col gap-4">
      {/* ===== Header ===== */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500/20 to-violet-500/20 border border-white/10">
            <Target className="w-6 h-6 text-cyan-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400">
              Docking Studio
            </h1>
            <p className="text-xs text-slate-400">Real AutoDock Vina &middot; Physics-based binding affinity</p>
          </div>
        </div>

        {/* History toggle */}
        <button
          onClick={() => { setShowHistory((v) => !v); if (!showHistory) loadHistory(); }}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-300 hover:bg-white/10 transition-colors"
        >
          <History className="w-3.5 h-3.5" />
          History
          {history.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 text-[10px] font-semibold">
              {history.length}
            </span>
          )}
        </button>
      </div>

      {/* ===== History Panel ===== */}
      {showHistory && (
        <div className="rounded-2xl border border-white/20 bg-white/5 backdrop-blur-md p-4 space-y-2 max-h-64 overflow-y-auto">
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">Job History</p>
            <button onClick={() => setShowHistory(false)} className="text-slate-500 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
          {historyLoading && (
            <div className="text-xs text-slate-500 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading...
            </div>
          )}
          {!historyLoading && history.length === 0 && (
            <p className="text-xs text-slate-500">No docking jobs yet.</p>
          )}
          {history.map((entry) => {
            const sCfg = STATUS_CONFIG[entry.status] || STATUS_CONFIG.idle;
            return (
              <div
                key={entry.task_id}
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-colors cursor-pointer group"
                onClick={() => handleHistoryReplay(entry)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`${sCfg.color}`}>
                    {STATUS_ICON[entry.status] || <FlaskConical className="w-3.5 h-3.5" />}
                  </span>
                  <span className="text-xs text-slate-300 font-mono truncate max-w-[180px]">
                    {entry.smiles}
                  </span>
                  <span className="text-[10px] text-slate-500 uppercase">{entry.target}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {entry.affinity_kcal_mol != null && (
                    <span className="text-xs text-emerald-400 font-semibold">
                      {entry.affinity_kcal_mol} kcal/mol
                    </span>
                  )}
                  {entry.elapsed_seconds != null && (
                    <span className="text-[10px] text-slate-500">{entry.elapsed_seconds}s</span>
                  )}
                  <span className="text-[10px] text-slate-600 opacity-0 group-hover:opacity-100 transition">
                    replay →
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ===== Input Form ===== */}
      <form onSubmit={handleRun} className="rounded-2xl border border-white/20 bg-white/5 backdrop-blur-md p-4 md:p-5 space-y-4">
        {/* Example SMILES chips */}
        <div className="flex flex-wrap gap-1.5">
          <span className="text-[10px] text-slate-500 uppercase tracking-wide self-center mr-1">Examples:</span>
          {EXAMPLE_SMILES.map((ex) => (
            <button
              key={ex.name}
              type="button"
              onClick={() => handleExampleClick(ex.smiles)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all border ${
                smiles === ex.smiles
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                  : 'bg-white/5 text-slate-400 border-white/10 hover:bg-white/10 hover:text-slate-200'
              }`}
            >
              {ex.name}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="md:col-span-2">
            <label className="block text-xs text-slate-400 mb-1">SMILES</label>
            <input
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              placeholder="Enter ligand SMILES"
              className="w-full px-3 py-2.5 rounded-xl bg-white/10 border border-white/20 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Target Protein</label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-white/10 border border-white/20 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            >
              {TARGET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-slate-900 text-white">
                  {option.label} — {option.desc}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Advanced: Exhaustiveness slider */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
          >
            <Sliders className="w-3 h-3" />
            Advanced Settings
            {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {showAdvanced && (
            <div className="mt-2 px-3 py-3 rounded-xl bg-white/5 border border-white/10 space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-slate-400">
                  Exhaustiveness
                  <span className="ml-1 text-[10px] text-slate-500">(search thoroughness)</span>
                </label>
                <span className="text-sm font-semibold text-cyan-300 tabular-nums min-w-[2ch] text-right">
                  {exhaustiveness}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={32}
                value={exhaustiveness}
                onChange={(e) => setExhaustiveness(Number(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-cyan-500 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-600">
                <span>1 (fast)</span>
                <span>8 (default)</span>
                <span>32 (thorough)</span>
              </div>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={!canRun}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 text-white text-sm font-semibold hover:from-cyan-500 hover:to-blue-500 transition-all shadow-lg shadow-cyan-500/20 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
          >
            {isSubmitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {isSubmitting ? 'Starting...' : 'Run Docking'}
          </button>

          {isProcessing && (
            <button
              type="button"
              onClick={handleCancel}
              disabled={isCancelling}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-rose-500/20 text-rose-300 border border-rose-500/30 text-sm font-medium hover:bg-rose-500/30 transition-colors disabled:opacity-50"
            >
              {isCancelling ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <StopCircle className="w-4 h-4" />
              )}
              {isCancelling ? 'Cancelling...' : 'Cancel'}
            </button>
          )}

          {(status === 'completed' || status === 'failed' || status === 'cancelled') && (
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-400 hover:bg-white/10 hover:text-slate-200 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset
            </button>
          )}
        </div>
      </form>

      {/* ===== Status & Results ===== */}
      <div className="rounded-2xl border border-white/20 bg-white/5 backdrop-blur-md p-4 md:p-5 space-y-3">
        {/* Status bar */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border ${statusCfg.bg} ${statusCfg.color} text-xs font-medium`}>
            {STATUS_ICON[status]}
            {statusCfg.label}
          </span>

          {taskId && (
            <span className="px-2 py-1 rounded-lg bg-white/5 border border-white/10 text-slate-400 font-mono text-[11px]">
              {taskId}
            </span>
          )}

          {/* Live timer during processing */}
          {isProcessing && (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs tabular-nums">
              <Clock className="w-3 h-3" />
              {elapsed.toFixed(1)}s
            </span>
          )}

          {/* Final elapsed */}
          {!isProcessing && result?.elapsed_seconds != null && (
            <span className="px-2 py-1 rounded-lg bg-white/5 border border-white/10 text-slate-400 text-xs">
              {result.elapsed_seconds}s
            </span>
          )}
        </div>

        {/* Progress bar during processing */}
        {isProcessing && (
          <div className="relative w-full h-1 rounded-full bg-white/5 overflow-hidden">
            <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full animate-pulse"
              style={{ width: `${Math.min(95, elapsed * 3)}%`, transition: 'width 0.5s ease-out' }}
            />
          </div>
        )}

        {/* Error */}
        {error && status !== 'cancelled' && (
          <div className="text-sm text-rose-300 border border-rose-500/30 bg-rose-500/10 rounded-xl p-3">
            {error}
          </div>
        )}

        {receptorError && (
          <div className="text-sm text-rose-300 border border-rose-500/30 bg-rose-500/10 rounded-xl p-3">
            {receptorError}
          </div>
        )}

        {/* Cancelled notice */}
        {status === 'cancelled' && (
          <div className="text-sm text-orange-300 border border-orange-500/30 bg-orange-500/10 rounded-xl p-3 inline-flex items-center gap-2">
            <Ban className="w-4 h-4 shrink-0" />
            Docking cancelled by user.
          </div>
        )}

        {/* ===== Results ===== */}
        {result?.status === 'completed' && (
          <>
            {/* Metrics row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="rounded-xl border border-white/20 bg-white/5 p-3">
                <p className="text-slate-400 text-xs">Affinity</p>
                <p className="text-xl font-bold text-emerald-400 tabular-nums">
                  {result.affinity_kcal_mol ?? '—'}
                  <span className="text-xs font-normal text-slate-400 ml-1">kcal/mol</span>
                </p>
              </div>
              <div className="rounded-xl border border-white/20 bg-white/5 p-3">
                <p className="text-slate-400 text-xs">Mode</p>
                <p className="font-semibold">
                  {result.mode === 'vina' ? (
                    <span className="inline-flex items-center gap-1 text-emerald-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      AutoDock Vina
                    </span>
                  ) : (
                    <span className="text-amber-400">{result.mode || '—'}</span>
                  )}
                </p>
              </div>
              <div className="rounded-xl border border-white/20 bg-white/5 p-3">
                <p className="text-slate-400 text-xs">Receptor</p>
                <p className="text-white font-semibold text-sm truncate">
                  {result.receptor_pdbqt || receptorInfo?.receptor_name || 'N/A'}
                </p>
              </div>
              <div className="rounded-xl border border-white/20 bg-white/5 p-3">
                <p className="text-slate-400 text-xs">Exhaustiveness</p>
                <p className="text-white font-semibold">{exhaustiveness}</p>
              </div>
            </div>

            {/* Download buttons */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleDownloadPose}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs font-medium hover:bg-emerald-500/20 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Download PDBQT
              </button>
              <button
                onClick={handleDownloadSummary}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-300 text-xs font-medium hover:bg-violet-500/20 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Download Summary
              </button>
            </div>

            {/* 3D Viewer */}
            <div>
              <p className="text-xs text-slate-400 mb-1">Docking Pose Overlay</p>
              <DockingPoseViewer
                receptorPdbqt={receptorPdbqt}
                ligandPdbqt={result.docked_ligand_pdbqt || ''}
                height={430}
              />
              {receptorInfo?.source && (
                <p className="text-[11px] text-slate-500 mt-2">
                  Receptor source: {receptorInfo.source}
                </p>
              )}
            </div>

            {/* Raw PDBQT (collapsible) */}
            <details className="group">
              <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-200 transition-colors select-none">
                Raw Docked Ligand PDBQT
              </summary>
              <textarea
                value={result.docked_ligand_pdbqt || ''}
                readOnly
                rows={8}
                className="mt-2 w-full px-3 py-2.5 rounded-xl bg-black/20 border border-white/20 text-xs text-slate-200 font-mono focus:outline-none resize-y"
              />
            </details>
          </>
        )}

        {/* Empty state */}
        {status === 'idle' && !taskId && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="p-3 rounded-full bg-gradient-to-br from-cyan-500/10 to-violet-500/10 border border-white/5 mb-3">
              <Sparkles className="w-6 h-6 text-cyan-400/60" />
            </div>
            <p className="text-sm text-slate-400">Enter a SMILES string and run docking to see real binding affinities.</p>
            <p className="text-[11px] text-slate-600 mt-1">Powered by AutoDock Vina 1.2.7</p>
          </div>
        )}
      </div>

      <HeavyComputeConfirm
        open={showConfirm}
        target={target}
        exhaustiveness={exhaustiveness}
        maxConcurrent={computePolicy?.max_docking_jobs}
        confirming={isSubmitting}
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleConfirmedRun}
      />
    </div>
  );
};

export default DockingStudio;
