/**
 * BatchProcessor — High-Throughput Screening module.
 *
 * Features:
 *   • Glass Dropzone (react-dropzone) for CSV / TXT / SMI files
 *   • PapaParse for instant browser-side CSV parsing
 *   • Calls POST /predict/batch with the full SMILES list + selected models
 *   • Real-time progress bar (animated gradient)
 *   • Glassmorphism data-grid with per-cell success / error badges
 *   • One-click CSV export of results via PapaParse unparse
 *   • Model selector with select-all toggle
 */

import React, { useState, useCallback, useMemo } from 'react';
import { useDropzone } from 'react-dropzone';
import Papa from 'papaparse';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UploadCloud,
  FileSpreadsheet,
  Loader2,
  Download,
  CheckCircle2,
  XCircle,
  Trash2,
  Play,
  FlaskConical,
  Beaker,
  AlertCircle,
  FileText,
  Zap,
} from 'lucide-react';

/* ── Model Catalogue (matches backend MODEL_REGISTRY keys) ─────── */
const MODEL_OPTIONS = [
  { id: 'solubility',    name: 'Solubility',     short: 'LogS',    color: 'text-blue-400' },
  { id: 'bbbp',          name: 'BBB Permeability', short: 'BBB',   color: 'text-violet-400' },
  { id: 'toxicity',      name: 'Toxicity',       short: 'Tox',     color: 'text-rose-400' },
  { id: 'cyp3a4',        name: 'CYP3A4',         short: 'CYP',     color: 'text-amber-400' },
  { id: 'half_life',     name: 'Half-Life',      short: 'T½',      color: 'text-emerald-400' },
  { id: 'cox2',          name: 'COX-2',          short: 'COX2',    color: 'text-cyan-400' },
  { id: 'hepg2',         name: 'HepG2',          short: 'HepG2',   color: 'text-pink-400' },
  { id: 'ace2',          name: 'ACE2',           short: 'ACE2',    color: 'text-teal-400' },
  { id: 'binding_score', name: 'Binding Score',  short: 'Bind',    color: 'text-orange-400' },
];

const ALL_MODEL_IDS = MODEL_OPTIONS.map(m => m.id);

/* ── Classification vs Regression buckets ──────────────────────── */
const CLASSIFICATION_MODELS = new Set(['toxicity', 'bbbp', 'cyp3a4', 'cox2', 'hepg2', 'ace2']);

/**
 * Formatting engine: translates raw prediction numbers into
 * human-readable badges (Analyzed mode) or clean decimals (Raw mode).
 *
 * Returns { text, className } for the table cell.
 */
const formatPrediction = (value, confidence, modelId, analyzed) => {
  if (value == null) return { text: '—', className: 'text-slate-600' };

  const isClassification = CLASSIFICATION_MODELS.has(modelId);

  // ── Raw mode: plain decimal ──
  // For classification models the backend sends value=0|1 (class label)
  // and confidence=P(predicted_class). Reconstruct the raw probability
  // of the positive class so scientists see e.g. 0.3133 instead of 0.0000.
  if (!analyzed) {
    let rawDisplay = value;
    if (isClassification && confidence != null) {
      // value >= 0.5 means predicted positive → P(pos) = confidence
      // value < 0.5  means predicted negative → P(pos) = 1 - confidence
      rawDisplay = value >= 0.5 ? confidence : (1 - confidence);
    }
    return {
      text: Number(rawDisplay).toFixed(4),
      className: 'font-mono text-slate-300',
      badge: false,
    };
  }

  // ── Analyzed mode ──
  const confFromServer = confidence != null ? Math.round(confidence * 100) : null;

  switch (modelId) {
    case 'toxicity': {
      const safe = value < 0.5;
      return {
        text: safe ? 'Safe' : 'Toxic',
        conf: confFromServer,
        className: safe
          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
          : 'bg-rose-500/10 text-rose-400 border border-rose-500/20',
        badge: true,
      };
    }
    case 'bbbp': {
      const perm = value >= 0.5;
      return {
        text: perm ? 'Permeable' : 'Non-Permeable',
        conf: confFromServer,
        className: perm
          ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20'
          : 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
        badge: true,
      };
    }
    case 'cyp3a4': {
      const inhib = value >= 0.5;
      return {
        text: inhib ? 'Inhibitor' : 'Non-Inhibitor',
        conf: confFromServer,
        className: inhib
          ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
          : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
        badge: true,
      };
    }
    case 'cox2': {
      const inhib = value >= 0.5;
      return {
        text: inhib ? 'Inhibitor' : 'Non-Inhibitor',
        conf: confFromServer,
        className: inhib
          ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
          : 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
        badge: true,
      };
    }
    case 'hepg2': {
      const safe = value < 0.5;
      return {
        text: safe ? 'Non-Toxic' : 'Toxic',
        conf: confFromServer,
        className: safe
          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
          : 'bg-pink-500/10 text-pink-400 border border-pink-500/20',
        badge: true,
      };
    }
    case 'ace2': {
      const binds = value >= 0.5;
      return {
        text: binds ? 'Binds' : 'Non-Binding',
        conf: confFromServer,
        className: binds
          ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20'
          : 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
        badge: true,
      };
    }
    case 'solubility':
      return {
        text: `${Number(value).toFixed(2)} LogS`,
        className: 'font-mono text-blue-300',
        badge: false,
      };
    case 'half_life':
      return {
        text: `${Number(value).toFixed(1)} hrs`,
        className: 'font-mono text-emerald-300',
        badge: false,
      };
    case 'binding_score':
      return {
        text: `${Number(value).toFixed(2)}`,
        className: 'font-mono text-orange-300',
        badge: false,
      };
    default:
      return {
        text: Number(value).toFixed(4),
        className: 'font-mono text-slate-300',
        badge: false,
      };
  }
};

/* ── Component ─────────────────────────────────────────────────── */
const BatchProcessor = () => {
  const [molecules, setMolecules] = useState([]);       // raw SMILES strings
  const [fileName, setFileName] = useState('');
  const [selectedModels, setSelectedModels] = useState([...ALL_MODEL_IDS]);
  const [results, setResults] = useState([]);            // array of MoleculeResult
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);           // 0-100
  const [error, setError] = useState(null);
  const [batchStats, setBatchStats] = useState(null);    // {total, succeeded, failed, time}
  const [isAnalyzedView, setIsAnalyzedView] = useState(true); // Analyzed (badges) vs Raw (decimals)

  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:5001';

  /* ── CSV Parsing (PapaParse in browser) ──────────────────────── */
  const onDrop = useCallback((acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setError(null);
    setResults([]);
    setBatchStats(null);

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (parsed) => {
        if (!parsed.data || parsed.data.length === 0) {
          setError('CSV file is empty or could not be parsed.');
          return;
        }

        // Find the SMILES column (case-insensitive)
        const headers = Object.keys(parsed.data[0]);
        const smilesKey = headers.find(h =>
          ['smiles', 'smi', 'molecule', 'canonical_smiles', 'compound'].includes(
            h.trim().toLowerCase(),
          ),
        ) || headers[0]; // fallback: first column

        const smilesList = parsed.data
          .map(row => row[smilesKey]?.trim())
          .filter(Boolean);

        if (smilesList.length === 0) {
          setError('No SMILES strings found. Make sure your CSV has a "SMILES" column.');
          return;
        }

        if (smilesList.length > 1000) {
          setError(`Too many molecules (${smilesList.length}). Maximum is 1,000 per batch.`);
          return;
        }

        setMolecules(smilesList);
        setFileName(file.name);
      },
      error: () => setError('Failed to parse CSV file.'),
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'text/plain': ['.txt', '.smi'],
    },
    multiple: false,
  });

  /* ── Model toggle ────────────────────────────────────────────── */
  const toggleModel = (id) => {
    setSelectedModels(prev =>
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id],
    );
  };

  const allSelected = selectedModels.length === ALL_MODEL_IDS.length;
  const toggleAll = () => {
    setSelectedModels(allSelected ? [] : [...ALL_MODEL_IDS]);
  };

  /* ── Run Batch ───────────────────────────────────────────────── */
  const runBatch = useCallback(async () => {
    if (molecules.length === 0 || selectedModels.length === 0) return;
    setIsRunning(true);
    setError(null);
    setResults([]);
    setBatchStats(null);
    setProgress(10); // show initial progress

    try {
      // Simulated progress while waiting for server
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 2, 90));
      }, 300);

      const res = await fetch(`${apiBase}/predict/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          smiles_list: molecules,
          models: selectedModels,
        }),
      });

      clearInterval(progressInterval);

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.error || errBody.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      setResults(data.results || []);
      setBatchStats({
        total: data.total,
        succeeded: data.succeeded,
        failed: data.failed,
        time: data.execution_time_ms,
      });
      setProgress(100);
    } catch (err) {
      console.error('[Batch]', err);
      setError(err.message || 'Batch processing failed. Check server logs.');
    } finally {
      setIsRunning(false);
    }
  }, [molecules, selectedModels, apiBase]);

  /* ── Export CSV ──────────────────────────────────────────────── */
  const exportCSV = useCallback(() => {
    if (results.length === 0) return;

    const rows = results.map(r => {
      const row = { SMILES: r.smiles, MW: r.molecular_weight, Status: r.status };
      selectedModels.forEach(modelId => {
        const m = MODEL_OPTIONS.find(o => o.id === modelId);
        const label = m?.name || modelId;
        const pred = r.predictions?.[modelId];
        if (pred?.error) {
          row[label] = `ERROR: ${pred.error}`;
        } else {
          row[label] = pred?.value ?? '';
          if (pred?.confidence != null) row[`${label} Conf`] = pred.confidence;
        }
      });
      if (r.error) row['Error'] = r.error;
      return row;
    });

    const csv = Papa.unparse(rows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `drugforge_batch_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }, [results, selectedModels]);

  /* ── Clear state ─────────────────────────────────────────────── */
  const handleClear = () => {
    setMolecules([]);
    setFileName('');
    setResults([]);
    setBatchStats(null);
    setError(null);
    setProgress(0);
  };

  /* ── Derived ─────────────────────────────────────────────────── */
  const hasResults = results.length > 0;
  const activeModels = useMemo(
    () => MODEL_OPTIONS.filter(m => selectedModels.includes(m.id)),
    [selectedModels],
  );

  /* ── Render ──────────────────────────────────────────────────── */
  return (
    <div className="min-h-screen p-4 md:p-8 pb-24">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* ═══ Header ═══ */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap justify-between items-end gap-4"
        >
          <div>
            <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400 flex items-center gap-3">
              <FlaskConical className="w-8 h-8 text-cyan-400" />
              High-Throughput Screening
            </h1>
            <p className="text-slate-400 mt-1">
              Drop a CSV of SMILES → run all 9 ADMET models → download results.
            </p>
          </div>
          {hasResults && (
            <button
              onClick={exportCSV}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl
                         bg-gradient-to-r from-cyan-500/20 to-violet-500/20
                         hover:from-cyan-500/30 hover:to-violet-500/30
                         border border-white/20 text-white transition-all"
            >
              <Download className="w-4 h-4" /> Export CSV
            </button>
          )}
        </motion.div>

        {/* ═══ Top Row: Dropzone + Model Selector ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* ── Glass Dropzone ── */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="lg:col-span-2 p-1 rounded-3xl bg-gradient-to-br from-white/10 to-white/5
                       backdrop-blur-xl border border-white/10 shadow-2xl"
          >
            {molecules.length === 0 ? (
              /* Drag-and-drop zone */
              <div
                {...getRootProps()}
                className={`
                  relative p-16 rounded-[22px] cursor-pointer
                  border-2 border-dashed transition-all duration-300
                  flex flex-col items-center justify-center text-center
                  ${isDragActive
                    ? 'border-cyan-400 bg-cyan-500/10 shadow-[0_0_40px_rgba(6,182,212,0.15)]'
                    : 'border-white/20 bg-black/10 hover:bg-white/5 hover:border-white/30'
                  }
                `}
              >
                <input {...getInputProps()} />

                {/* Animated glow ring */}
                {isDragActive && (
                  <div className="absolute inset-0 rounded-[22px] animate-pulse
                                  bg-gradient-to-r from-cyan-500/5 via-violet-500/5 to-cyan-500/5" />
                )}

                <div className={`p-5 rounded-2xl mb-5 transition-all duration-300
                  ${isDragActive
                    ? 'bg-cyan-500/20 shadow-[0_0_20px_rgba(6,182,212,0.3)]'
                    : 'bg-white/5'}`}
                >
                  <UploadCloud className={`w-14 h-14 transition-colors duration-300
                    ${isDragActive ? 'text-cyan-400' : 'text-slate-500'}`}
                  />
                </div>

                <h3 className="text-xl font-semibold text-white mb-2">
                  {isDragActive ? 'Drop your file here...' : 'Drag & Drop your CSV file'}
                </h3>
                <p className="text-slate-400 text-sm max-w-md mb-4">
                  or <span className="text-cyan-400 underline underline-offset-2">click to browse</span>
                </p>

                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><FileSpreadsheet className="w-3.5 h-3.5" /> .csv</span>
                  <span className="flex items-center gap-1"><FileText className="w-3.5 h-3.5" /> .txt</span>
                  <span className="flex items-center gap-1"><Beaker className="w-3.5 h-3.5" /> .smi</span>
                </div>

                <p className="text-slate-500 text-xs mt-4 max-w-sm">
                  File must have a header row with a column named{' '}
                  <code className="text-cyan-400 bg-black/30 px-1.5 py-0.5 rounded font-mono">SMILES</code>.
                  Up to 1,000 compounds per batch.
                </p>
              </div>
            ) : (
              /* File loaded indicator */
              <div className="p-8 rounded-[22px] bg-black/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-emerald-500/15">
                      <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-white">{fileName}</h3>
                      <p className="text-sm text-slate-400">
                        <span className="text-cyan-400 font-mono">{molecules.length}</span> molecules ready
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={handleClear}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm
                               text-slate-400 hover:text-rose-400 hover:bg-rose-500/10
                               border border-transparent hover:border-rose-500/20 transition-all"
                  >
                    <Trash2 className="w-4 h-4" /> Clear
                  </button>
                </div>

                {/* Preview first 5 SMILES */}
                <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-2">
                  {molecules.slice(0, 6).map((smi, i) => (
                    <div key={i} className="px-3 py-2 rounded-lg bg-white/5 border border-white/5
                                            text-xs font-mono text-slate-300 truncate">
                      {smi}
                    </div>
                  ))}
                  {molecules.length > 6 && (
                    <div className="px-3 py-2 rounded-lg bg-white/5 border border-white/5
                                    text-xs text-slate-500 flex items-center justify-center">
                      +{molecules.length - 6} more
                    </div>
                  )}
                </div>
              </div>
            )}
          </motion.div>

          {/* ── Model Selector ── */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="p-6 rounded-2xl bg-white/5 backdrop-blur-xl
                       border border-white/10 shadow-xl flex flex-col"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider">
                Models
              </h3>
              <button
                onClick={toggleAll}
                className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                {allSelected ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            <div className="space-y-1.5 flex-1 overflow-y-auto">
              {MODEL_OPTIONS.map(model => {
                const isSelected = selectedModels.includes(model.id);
                return (
                  <label
                    key={model.id}
                    className={`
                      flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer
                      transition-all duration-200 text-sm
                      ${isSelected
                        ? 'bg-cyan-500/10 border border-cyan-500/25'
                        : 'bg-transparent border border-transparent hover:bg-white/5'
                      }
                    `}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleModel(model.id)}
                      className="rounded border-white/30 bg-black/20 text-cyan-500
                                 focus:ring-cyan-500 focus:ring-offset-0"
                    />
                    <span className={`font-medium ${isSelected ? model.color : 'text-slate-400'}`}>
                      {model.name}
                    </span>
                  </label>
                );
              })}
            </div>

            {/* Run Button */}
            <button
              onClick={runBatch}
              disabled={isRunning || molecules.length === 0 || selectedModels.length === 0}
              className="mt-4 w-full flex items-center justify-center gap-2.5 py-3 rounded-xl
                         font-semibold text-sm transition-all duration-300
                         disabled:opacity-40 disabled:cursor-not-allowed
                         bg-gradient-to-r from-cyan-500 to-violet-500
                         hover:from-cyan-400 hover:to-violet-400
                         shadow-[0_4px_20px_rgba(6,182,212,0.3)]
                         text-white"
            >
              {isRunning ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Processing...</>
              ) : (
                <><Zap className="w-4 h-4" /> Run {molecules.length} × {selectedModels.length} Predictions</>
              )}
            </button>

            {hasResults && (
              <button
                onClick={exportCSV}
                className="mt-2 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl
                           text-sm text-slate-300 hover:text-white bg-white/5 hover:bg-white/10
                           border border-white/10 transition-all"
              >
                <Download className="w-4 h-4" /> Download CSV
              </button>
            )}
          </motion.div>
        </div>

        {/* ═══ Error Banner ═══ */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/25
                         flex items-center gap-3 text-rose-400 text-sm"
            >
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
              <button
                onClick={() => setError(null)}
                className="ml-auto text-rose-400/60 hover:text-rose-300"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ═══ Progress Bar ═══ */}
        <AnimatePresence>
          {isRunning && (
            <motion.div
              initial={{ opacity: 0, scaleY: 0 }}
              animate={{ opacity: 1, scaleY: 1 }}
              exit={{ opacity: 0, scaleY: 0 }}
              className="p-5 rounded-2xl bg-white/5 backdrop-blur-xl border border-white/10"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-slate-400 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                  Analyzing {molecules.length} molecules across {selectedModels.length} models...
                </span>
                <span className="text-sm font-mono text-cyan-400">{progress}%</span>
              </div>
              <div className="h-2 bg-black/30 rounded-full overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-500 to-cyan-400
                             bg-[length:200%_100%] animate-[shimmer_2s_linear_infinite]"
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.3, ease: 'easeOut' }}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ═══ Batch Stats ═══ */}
        <AnimatePresence>
          {batchStats && !isRunning && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="grid grid-cols-2 md:grid-cols-4 gap-4"
            >
              {[
                { label: 'Total', value: batchStats.total, color: 'text-white' },
                { label: 'Succeeded', value: batchStats.succeeded, color: 'text-emerald-400' },
                { label: 'Failed', value: batchStats.failed, color: batchStats.failed > 0 ? 'text-rose-400' : 'text-slate-500' },
                { label: 'Time', value: `${(batchStats.time / 1000).toFixed(1)}s`, color: 'text-cyan-400' },
              ].map(stat => (
                <div key={stat.label} className="p-4 rounded-xl bg-white/5 border border-white/10 text-center">
                  <div className={`text-2xl font-bold font-mono ${stat.color}`}>{stat.value}</div>
                  <div className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{stat.label}</div>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ═══ Results Data Grid ═══ */}
        <AnimatePresence>
          {hasResults && !isRunning && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-2xl bg-white/5 backdrop-blur-xl border border-white/10
                         shadow-2xl overflow-hidden"
            >
              {/* Table header with Raw / Analyzed toggle */}
              <div className="px-6 py-4 bg-black/20 border-b border-white/5
                              flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <FileSpreadsheet className="w-5 h-5 text-cyan-400" />
                  Results
                </h3>

                <div className="flex items-center gap-4">
                  <span className="text-xs text-slate-500 font-mono">
                    {results.length} molecules × {activeModels.length} models
                  </span>

                  {/* View Toggle */}
                  <div className="flex bg-black/40 p-1 rounded-lg border border-white/10 backdrop-blur-md">
                    <button
                      onClick={() => setIsAnalyzedView(false)}
                      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                        !isAnalyzedView
                          ? 'bg-white/10 text-cyan-400 shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Raw Data
                    </button>
                    <button
                      onClick={() => setIsAnalyzedView(true)}
                      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                        isAnalyzedView
                          ? 'bg-white/10 text-cyan-400 shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Analyzed
                    </button>
                  </div>
                </div>
              </div>

              {/* Scrollable table */}
              <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
                <table className="w-full text-sm min-w-[800px]">
                  <thead className="sticky top-0 z-10">
                    <tr className="bg-black/40 backdrop-blur-md">
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400
                                     uppercase tracking-wider w-8">#</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400
                                     uppercase tracking-wider">SMILES</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400
                                     uppercase tracking-wider">MW</th>
                      {activeModels.map(m => (
                        <th key={m.id} className={`px-4 py-3 text-left text-xs font-medium
                                     uppercase tracking-wider ${m.color}`}>
                          {m.short}
                        </th>
                      ))}
                      <th className="px-4 py-3 text-center text-xs font-medium text-slate-400
                                     uppercase tracking-wider w-16">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {results.map((row, idx) => (
                      <tr
                        key={idx}
                        className="hover:bg-white/5 transition-colors duration-150"
                      >
                        <td className="px-4 py-3 text-slate-600 text-xs font-mono">{idx + 1}</td>
                        <td className="px-4 py-3 font-mono text-xs text-cyan-300 max-w-[220px] truncate"
                            title={row.smiles}>
                          {row.smiles}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400 font-mono">
                          {row.molecular_weight != null ? row.molecular_weight.toFixed(1) : '—'}
                        </td>
                        {activeModels.map(m => {
                          const pred = row.predictions?.[m.id];
                          if (!pred) {
                            return <td key={m.id} className="px-4 py-3 text-slate-600">—</td>;
                          }
                          if (pred.error) {
                            return (
                              <td key={m.id} className="px-4 py-3">
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded
                                                 text-xs bg-rose-500/15 text-rose-400" title={pred.error}>
                                  <XCircle className="w-3 h-3" /> err
                                </span>
                              </td>
                            );
                          }

                          const fmt = formatPrediction(pred.value, pred.confidence, m.id, isAnalyzedView);

                          return (
                            <td key={m.id} className="px-4 py-3 text-xs">
                              {fmt.badge ? (
                                <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${fmt.className}`}>
                                  {fmt.text}
                                  {fmt.conf != null && (
                                    <span className="opacity-60 ml-0.5">({fmt.conf}%)</span>
                                  )}
                                </span>
                              ) : (
                                <span className={fmt.className}>{fmt.text}</span>
                              )}
                            </td>
                          );
                        })}
                        <td className="px-4 py-3 text-center">
                          {row.status === 'success' ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 mx-auto" />
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-rose-400" title={row.error}>
                              <XCircle className="w-3.5 h-3.5" />
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ═══ Empty State (no file, no results) ═══ */}
        {molecules.length === 0 && !hasResults && !error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="text-center py-16"
          >
            <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl
                            bg-white/5 border border-white/10 text-slate-500 text-sm mb-6">
              <FlaskConical className="w-4 h-4" />
              How it works
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mx-auto mt-4">
              {[
                { step: '1', title: 'Upload CSV', desc: 'Drop a file with a SMILES column' },
                { step: '2', title: 'Select Models', desc: 'Choose which ADMET models to run' },
                { step: '3', title: 'Get Results', desc: 'Download predictions as CSV' },
              ].map(s => (
                <div key={s.step} className="p-6 rounded-xl bg-white/5 border border-white/10">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-r from-cyan-500 to-violet-500
                                  flex items-center justify-center text-white text-sm font-bold mb-3 mx-auto">
                    {s.step}
                  </div>
                  <h4 className="text-white font-medium mb-1">{s.title}</h4>
                  <p className="text-slate-500 text-sm">{s.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default BatchProcessor;
