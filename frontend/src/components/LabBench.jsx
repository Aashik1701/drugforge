import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FlaskConical, Shield, AlertCircle, Pill, Clock, Target,
  Microscope, Brain, BarChart3, Search, Play, Loader2,
  CheckCircle2, XCircle, Download, ChevronDown, Atom,
  FileText, RotateCcw, Info, Clipboard
} from 'lucide-react';
import GlassCard, { GlassPanel, GlassButton, GlassBadge } from './ui/GlassCard';
import { ShimmerBlock, ShimmerText } from './ui/ShimmerLoader';
import RDKitMolecularVisualization from './RDKitMolecularVisualization';
import Molecule3DViewer from './Molecule3DViewer';
import { useDrugForge } from '../context/DrugForgeContext';

// ────────────────────────────────────────────────────────────
//  MODEL DEFINITIONS
// ────────────────────────────────────────────────────────────
const ADMET_MODELS = [
  {
    id: 'solubility', name: 'Solubility (LogS)', icon: FlaskConical,
    endpoint: '/predict/solubility', color: 'cyan',
    formatResult: (d) => ({
      value: d.prediction ?? d.logS ?? d.solubility ?? '—',
      label: 'LogS',
      unit: 'mol/L',
      interpret: (v) => {
        const n = parseFloat(v);
        if (isNaN(n)) return { text: 'Unknown', color: 'gray' };
        if (n >= 0) return { text: 'Highly Soluble', color: 'emerald' };
        if (n > -2) return { text: 'Soluble', color: 'cyan' };
        if (n > -4) return { text: 'Moderate', color: 'amber' };
        return { text: 'Poorly Soluble', color: 'rose' };
      },
    }),
  },
  {
    id: 'toxicity', name: 'Toxicity', icon: AlertCircle,
    endpoint: '/predict/toxicity', color: 'rose',
    formatResult: (d) => ({
      value: d.prediction ?? d.toxicity ?? d['Predicted Class'] ?? '—',
      label: 'Toxic',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('non') || s === '0' || s === 'false') return { text: 'Non-Toxic', color: 'emerald' };
        return { text: 'Toxic', color: 'rose' };
      },
    }),
  },
  {
    id: 'bbbp', name: 'BBB Permeability', icon: Shield,
    endpoint: '/predict/bbbp', color: 'violet',
    formatResult: (d) => ({
      value: d.prediction ?? d.bbbp ?? d['Predicted Class'] ?? '—',
      label: 'BBB',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('permeable') || s === '1' || s === 'true' || s === 'yes')
          return { text: 'Permeable', color: 'emerald' };
        return { text: 'Non-Permeable', color: 'rose' };
      },
    }),
  },
  {
    id: 'cyp3a4', name: 'CYP3A4 Inhibition', icon: Pill,
    endpoint: '/predict/cyp3a4', color: 'amber',
    formatResult: (d) => ({
      value: d.prediction ?? d.cyp3a4 ?? d['Predicted Class'] ?? '—',
      label: 'CYP3A4',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('inhibitor') || s === '1' || s === 'true')
          return { text: 'Inhibitor', color: 'rose' };
        return { text: 'Non-Inhibitor', color: 'emerald' };
      },
    }),
  },
  {
    id: 'half-life', name: 'Half-Life', icon: Clock,
    endpoint: '/predict/half-life', color: 'teal',
    formatResult: (d) => ({
      value: d.prediction ?? d.half_life ?? d['Predicted Class'] ?? '—',
      label: 'T½',
      unit: 'hours',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('long') || parseFloat(v) > 6) return { text: 'Long', color: 'emerald' };
        if (s.includes('short') || parseFloat(v) < 2) return { text: 'Short', color: 'amber' };
        return { text: 'Moderate', color: 'cyan' };
      },
    }),
  },
];

const TARGET_MODELS = [
  {
    id: 'ace2', name: 'ACE2 Binding', icon: Brain,
    endpoint: '/predict/ace2', color: 'violet',
    formatResult: (d) => ({
      value: d.prediction ?? d.ace2 ?? d['Predicted Class'] ?? '—',
      label: 'ACE2',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('active') || s === '1') return { text: 'Active Binder', color: 'emerald' };
        return { text: 'Inactive', color: 'gray' };
      },
    }),
  },
  {
    id: 'cox2', name: 'COX-2 Binding', icon: Target,
    endpoint: '/predict/cox2', color: 'emerald',
    formatResult: (d) => ({
      value: d.prediction ?? d.cox2 ?? d['Predicted Class'] ?? '—',
      label: 'COX-2',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('active') || s === '1') return { text: 'Active', color: 'emerald' };
        return { text: 'Inactive', color: 'gray' };
      },
    }),
  },
  {
    id: 'binding-score', name: 'Binding Score', icon: BarChart3,
    endpoint: '/predict/binding-score', color: 'cyan',
    formatResult: (d) => ({
      value: d.prediction ?? d.binding_score ?? d.score ?? '—',
      label: 'Score',
      interpret: (v) => {
        const n = parseFloat(v);
        if (isNaN(n)) return { text: 'Unknown', color: 'gray' };
        if (n > 7) return { text: 'Strong', color: 'emerald' };
        if (n > 5) return { text: 'Moderate', color: 'amber' };
        return { text: 'Weak', color: 'rose' };
      },
    }),
  },
  {
    id: 'hepg2', name: 'HepG2 Cytotoxicity', icon: Microscope,
    endpoint: '/predict/hepg2', color: 'sky',
    formatResult: (d) => ({
      value: d.prediction ?? d.hepg2 ?? d['Predicted Class'] ?? '—',
      label: 'HepG2',
      interpret: (v) => {
        const s = String(v).toLowerCase();
        if (s.includes('toxic') || s === '1') return { text: 'Cytotoxic', color: 'rose' };
        return { text: 'Non-Cytotoxic', color: 'emerald' };
      },
    }),
  },
];

const ALL_MODELS = [...ADMET_MODELS, ...TARGET_MODELS];

// ────────────────────────────────────────────────────────────
//  QUICK STATS FROM RESPONSE (MW, LogP, TPSA if returned)
// ────────────────────────────────────────────────────────────
const extractQuickStats = (results) => {
  const stats = {};
  for (const [, res] of Object.entries(results)) {
    if (res.raw) {
      if (res.raw.molecular_weight ?? res.raw.MW) stats.MW = res.raw.molecular_weight ?? res.raw.MW;
      if (res.raw.logP ?? res.raw.LogP) stats.LogP = res.raw.logP ?? res.raw.LogP;
      if (res.raw.tpsa ?? res.raw.TPSA) stats.TPSA = res.raw.tpsa ?? res.raw.TPSA;
    }
  }
  return stats;
};

// ────────────────────────────────────────────────────────────
//  RESULT CARD COMPONENT
// ────────────────────────────────────────────────────────────
const ResultCard = ({ model, result, isLoading }) => {
  const Icon = model.icon;

  if (isLoading) {
    return (
      <GlassCard className="p-5" hoverable={false}>
        <div className="flex items-center gap-3 mb-3">
          <div className={`w-8 h-8 rounded-lg bg-${model.color}-500/20 flex items-center justify-center`}>
            <Icon className={`w-4 h-4 text-${model.color}-500`} />
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{model.name}</span>
        </div>
        <ShimmerBlock className="w-2/3 h-8 mb-2" />
        <ShimmerBlock className="w-1/2 h-4" />
      </GlassCard>
    );
  }

  if (result?.error) {
    return (
      <GlassCard className="p-5 border-rose-500/20" hoverable={false}>
        <div className="flex items-center gap-3 mb-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-rose-500/20">
            <XCircle className="w-4 h-4 text-rose-500" />
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{model.name}</span>
        </div>
        <p className="text-xs truncate text-rose-500">{result.error}</p>
      </GlassCard>
    );
  }

  if (!result) return null;

  const formatted = model.formatResult(result.raw || {});
  const interp = formatted.interpret(formatted.value);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      <GlassCard className="p-5" hoverable>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg bg-${model.color}-500/20 flex items-center justify-center`}>
              <Icon className={`w-4 h-4 text-${model.color}-500`} />
            </div>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{model.name}</span>
          </div>
          <GlassBadge variant={
            interp.color === 'emerald' ? 'success' :
            interp.color === 'rose' ? 'danger' :
            interp.color === 'amber' ? 'warning' : 'primary'
          }>
            {interp.text}
          </GlassBadge>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-2xl font-semibold text-gray-900 dark:text-white">
            {typeof formatted.value === 'number' ? formatted.value.toFixed(3) : String(formatted.value)}
          </span>
          {formatted.unit && (
            <span className="text-xs text-gray-400">{formatted.unit}</span>
          )}
        </div>
      </GlassCard>
    </motion.div>
  );
};

// ────────────────────────────────────────────────────────────
//  MAIN LAB BENCH COMPONENT
// ────────────────────────────────────────────────────────────
const LabBench = () => {
  const [searchParams] = useSearchParams();
  const [smiles, setSmiles] = useState(searchParams.get('smiles') || '');
  const [activeTab, setActiveTab] = useState('admet');
  const [results, setResults] = useState({});
  const [runningModels, setRunningModels] = useState(new Set());
  const [hasRun, setHasRun] = useState(false);
  const [viewMode, setViewMode] = useState('3d'); // '2d' | '3d'
  const inputRef = useRef(null);

  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:5001';
  const { setActiveContext } = useDrugForge();

  // Auto-analyze if smiles came from URL params
  useEffect(() => {
    const urlSmiles = searchParams.get('smiles');
    if (urlSmiles) {
      setSmiles(urlSmiles);
      // small delay to let component mount
      const timer = setTimeout(() => runAllModels(urlSmiles), 300);
      return () => clearTimeout(timer);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Tell the AI Chat what we're analyzing ──────────────
  useEffect(() => {
    if (smiles && Object.keys(results).length > 0) {
      setActiveContext({
        smiles,
        results,
        activeTab,
        timestamp: new Date().toISOString(),
      });
    }
  }, [smiles, results, activeTab, setActiveContext]);

  const currentModels = activeTab === 'admet' ? ADMET_MODELS : TARGET_MODELS;

  // ─── Run a single model ──────────────────────────────
  const runModel = useCallback(async (model, smilesInput) => {
    setRunningModels(prev => new Set(prev).add(model.id));
    try {
      const res = await fetch(`${apiBase}${model.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ smiles: smilesInput }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setResults(prev => ({ ...prev, [model.id]: { raw: data } }));
    } catch (err) {
      setResults(prev => ({ ...prev, [model.id]: { error: err.message } }));
    } finally {
      setRunningModels(prev => {
        const next = new Set(prev);
        next.delete(model.id);
        return next;
      });
    }
  }, [apiBase]);

  // ─── Run all models (ADMET + Targets) simultaneously ──
  const runAllModels = useCallback((smilesInput) => {
    const s = (smilesInput || smiles).trim();
    if (!s) return;
    setHasRun(true);
    setResults({});
    // Save to recent
    try {
      const recent = JSON.parse(localStorage.getItem('drugforge_recent') || '[]');
      const updated = [
        { smiles: s, type: 'Full Analysis', time: new Date().toLocaleTimeString() },
        ...recent.filter(r => r.smiles !== s),
      ].slice(0, 10);
      localStorage.setItem('drugforge_recent', JSON.stringify(updated));
    } catch { /* ignore */ }
    ALL_MODELS.forEach(model => runModel(model, s));
  }, [smiles, runModel]);

  // ─── Run current tab's models only ─────────────────────
  const runTabModels = useCallback(() => {
    const s = smiles.trim();
    if (!s) return;
    setHasRun(true);
    currentModels.forEach(model => {
      // Clear old result for this model
      setResults(prev => {
        const next = { ...prev };
        delete next[model.id];
        return next;
      });
      runModel(model, s);
    });
  }, [smiles, currentModels, runModel]);

  const handleSubmit = (e) => {
    e.preventDefault();
    runAllModels();
  };

  const handleReset = () => {
    setSmiles('');
    setResults({});
    setRunningModels(new Set());
    setHasRun(false);
    inputRef.current?.focus();
  };

  const copySmiles = () => {
    navigator.clipboard.writeText(smiles);
  };

  const quickStats = useMemo(() => extractQuickStats(results), [results]);
  const anyLoading = runningModels.size > 0;

  // Count completed
  const admetDone = ADMET_MODELS.filter(m => results[m.id]).length;
  const targetDone = TARGET_MODELS.filter(m => results[m.id]).length;

  return (
    <div className="min-h-screen pb-24">
      <div className="p-4 mx-auto max-w-7xl md:p-8">

        {/* ─── TOP: Input Bar ─────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <GlassPanel className="p-5">
            <form onSubmit={handleSubmit} className="flex flex-col gap-4 md:flex-row">
              <div className="relative flex-1">
                <Atom className="absolute w-5 h-5 -translate-y-1/2 left-4 top-1/2 text-cyan-500" />
                <input
                  ref={inputRef}
                  type="text"
                  value={smiles}
                  onChange={(e) => setSmiles(e.target.value)}
                  placeholder="Paste SMILES notation here…"
                  className="w-full pl-12 pr-12 font-mono text-lg text-gray-900 placeholder-gray-400 transition-all duration-200 border h-14 rounded-xl bg-white/30 dark:bg-black/30 backdrop-blur-md border-white/20 dark:border-gray-700/30 dark:text-gray-100 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
                />
                {smiles && (
                  <button
                    type="button"
                    onClick={copySmiles}
                    className="absolute p-2 text-gray-400 transition-colors -translate-y-1/2 right-3 top-1/2 hover:text-cyan-500"
                    title="Copy SMILES"
                  >
                    <Clipboard className="w-4 h-4" />
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <GlassButton
                  type="submit"
                  variant="primary"
                  disabled={!smiles.trim() || anyLoading}
                  className="flex items-center gap-2 px-8 h-14"
                >
                  {anyLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Play className="w-5 h-5" />
                  )}
                  {anyLoading ? 'Running…' : 'Run All'}
                </GlassButton>
                {hasRun && (
                  <GlassButton
                    type="button"
                    variant="ghost"
                    onClick={handleReset}
                    className="px-4 h-14"
                    title="Reset"
                  >
                    <RotateCcw className="w-5 h-5" />
                  </GlassButton>
                )}
              </div>
            </form>

            {/* Quick Stats Tags */}
            {Object.keys(quickStats).length > 0 && (
              <div className="flex flex-wrap gap-3 mt-4">
                {Object.entries(quickStats).map(([key, val]) => (
                  <GlassBadge key={key} variant="default">
                    {key}: <span className="ml-1 font-mono">{typeof val === 'number' ? val.toFixed(2) : val}</span>
                  </GlassBadge>
                ))}
              </div>
            )}
          </GlassPanel>
        </motion.div>

        {/* ─── Split Layout: Structure Viewer + Results ─── */}
        {hasRun && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="grid grid-cols-1 gap-6 lg:grid-cols-12"
          >
            {/* LEFT: Sticky Structure Viewer (2D / 3D toggle) */}
            <div className="lg:col-span-4">
              <GlassCard className="sticky p-0 top-24">
                {/* Header with 2D / 3D toggle */}
                <div className="flex items-center justify-between p-4 border-b border-white/10 bg-white/5">
                  <h3 className="flex items-center text-lg font-semibold text-slate-700 dark:text-slate-200">
                    <Atom className="w-5 h-5 mr-2 text-bio-teal" />
                    Structure Viewer
                  </h3>
                  <div className="flex rounded-lg border border-white/20 overflow-hidden text-xs font-medium">
                    <button
                      onClick={() => setViewMode('2d')}
                      className={`px-3 py-1.5 transition-all ${
                        viewMode === '2d'
                          ? 'bg-cyan-500/20 text-cyan-600 dark:text-cyan-300'
                          : 'text-slate-400 hover:bg-white/10'
                      }`}
                    >
                      2D
                    </button>
                    <button
                      onClick={() => setViewMode('3d')}
                      className={`px-3 py-1.5 transition-all ${
                        viewMode === '3d'
                          ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-300'
                          : 'text-slate-400 hover:bg-white/10'
                      }`}
                    >
                      3D
                    </button>
                  </div>
                </div>

                {/* Molecule Render */}
                <div className="bg-white/50 dark:bg-black/40 min-h-[300px] flex items-center justify-center">
                  {smiles ? (
                    viewMode === '3d' ? (
                      <Molecule3DViewer
                        smiles={smiles}
                        width={350}
                        height={300}
                        spin={true}
                        showControls={false}
                      />
                    ) : (
                      <RDKitMolecularVisualization
                        smiles={smiles}
                        width={350}
                        height={300}
                        showControls={false}
                        showProperties={false}
                      />
                    )
                  ) : (
                    <div className="p-8 text-sm italic text-slate-400">
                      Enter a SMILES string to view structure
                    </div>
                  )}
                </div>

                {/* Quick Stats overlay from results */}
                {Object.keys(quickStats).length > 0 && (
                  <div className="grid grid-cols-2 gap-2 p-4 text-xs border-t border-white/10">
                    {Object.entries(quickStats).slice(0, 4).map(([key, val]) => (
                      <div key={key} className="p-2 text-center rounded-lg bg-white/20 dark:bg-black/20">
                        <span className="block text-slate-500 dark:text-slate-400">{key}</span>
                        <span className="font-mono font-bold text-slate-700 dark:text-slate-200">
                          {typeof val === 'number' ? val.toFixed(2) : val}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </GlassCard>
            </div>

            {/* RIGHT: Tab Bar + Results Grid */}
            <div className="lg:col-span-8">
            {/* Tab Bar */}
            <div className="flex items-center gap-2 mb-6">
              {[
                { key: 'admet', label: 'ADMET', count: `${admetDone}/${ADMET_MODELS.length}` },
                { key: 'targets', label: 'Targets', count: `${targetDone}/${TARGET_MODELS.length}` },
                { key: 'report', label: 'Report', count: null },
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`
                    px-5 py-2.5 rounded-xl text-sm font-medium
                    border backdrop-blur-md transition-all duration-200
                    ${activeTab === tab.key
                      ? 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300 border-cyan-500/30 shadow-glow-cyan'
                      : 'bg-white/10 dark:bg-black/10 text-gray-500 dark:text-gray-400 border-white/20 dark:border-gray-700/20 hover:bg-white/20'
                    }
                  `}
                >
                  {tab.label}
                  {tab.count && (
                    <span className="ml-2 text-xs opacity-60">{tab.count}</span>
                  )}
                </button>
              ))}

              {/* Re-run current tab */}
              <GlassButton
                variant="ghost"
                onClick={runTabModels}
                disabled={anyLoading || !smiles.trim()}
                className="px-4 py-2 ml-auto text-xs"
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1.5 inline" />
                Re-run {activeTab === 'admet' ? 'ADMET' : activeTab === 'targets' ? 'Targets' : ''}
              </GlassButton>
            </div>

            {/* Tab Content */}
            <AnimatePresence mode="wait">
              {activeTab === 'report' ? (
                <ReportTab key="report" smiles={smiles} results={results} models={ALL_MODELS} />
              ) : (
                <motion.div
                  key={activeTab}
                  initial={{ opacity: 0, x: activeTab === 'admet' ? -20 : 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: activeTab === 'admet' ? 20 : -20 }}
                  transition={{ duration: 0.2 }}
                  className="grid grid-cols-1 gap-4 md:grid-cols-2"
                >
                  {currentModels.map(model => (
                    <ResultCard
                      key={model.id}
                      model={model}
                      result={results[model.id]}
                      isLoading={runningModels.has(model.id)}
                    />
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
            </div>{/* end RIGHT col */}
          </motion.div>
        )}

        {/* ─── Empty State ────────────────────────────────── */}
        {!hasRun && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="py-24 text-center"
          >
            <Atom className="w-16 h-16 mx-auto mb-6 text-cyan-500/30" />
            <h2 className="mb-3 text-2xl font-thin text-gray-600 dark:text-gray-400">
              Paste a SMILES to begin
            </h2>
            <p className="max-w-md mx-auto mb-8 text-sm text-gray-400 dark:text-gray-500">
              All 9 models will run simultaneously. Results appear as they complete.
            </p>
            <div className="flex flex-wrap justify-center max-w-lg gap-2 mx-auto">
              {[
                { label: 'Aspirin', smiles: 'CC(=O)Oc1ccccc1C(=O)O' },
                { label: 'Caffeine', smiles: 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C' },
                { label: 'Ethanol', smiles: 'CCO' },
                { label: 'Ibuprofen', smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O' },
              ].map(ex => (
                <button
                  key={ex.label}
                  onClick={() => { setSmiles(ex.smiles); }}
                  className="px-4 py-2 text-sm text-gray-600 transition-all duration-200 border rounded-full bg-white/10 dark:bg-black/10 border-white/20 dark:border-gray-700/20 backdrop-blur-md dark:text-gray-300 hover:bg-cyan-500/10 hover:border-cyan-500/30 hover:text-cyan-600 dark:hover:text-cyan-400"
                >
                  {ex.label}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

// ────────────────────────────────────────────────────────────
//  REPORT TAB
// ────────────────────────────────────────────────────────────
const ReportTab = ({ smiles, results, models }) => {
  const completedCount = models.filter(m => results[m.id] && !results[m.id]?.error).length;
  const errorCount = models.filter(m => results[m.id]?.error).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <GlassPanel className="p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h3 className="mb-1 text-xl font-medium text-gray-800 dark:text-gray-200">
              Analysis Report
            </h3>
            <code className="font-mono text-sm text-gray-500 dark:text-gray-400">
              {smiles}
            </code>
          </div>
          <GlassButton variant="primary" onClick={() => window.print()} className="flex items-center gap-2">
            <Download className="w-4 h-4" />
            Export
          </GlassButton>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="p-4 text-center rounded-xl bg-white/10 dark:bg-black/10">
            <span className="block text-2xl font-bold text-gray-900 dark:text-white">{completedCount}</span>
            <span className="text-xs text-gray-500">Completed</span>
          </div>
          <div className="p-4 text-center rounded-xl bg-white/10 dark:bg-black/10">
            <span className="block text-2xl font-bold text-gray-900 dark:text-white">{errorCount}</span>
            <span className="text-xs text-gray-500">Failed</span>
          </div>
          <div className="p-4 text-center rounded-xl bg-white/10 dark:bg-black/10">
            <span className="block text-2xl font-bold text-gray-900 dark:text-white">{models.length - completedCount - errorCount}</span>
            <span className="text-xs text-gray-500">Pending</span>
          </div>
        </div>

        {/* Results Table */}
        <div className="overflow-hidden border rounded-xl border-white/10 dark:border-gray-700/20">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-white/5 dark:bg-black/10">
                <th className="px-4 py-3 font-medium text-left text-gray-500 dark:text-gray-400">Model</th>
                <th className="px-4 py-3 font-medium text-left text-gray-500 dark:text-gray-400">Result</th>
                <th className="px-4 py-3 font-medium text-left text-gray-500 dark:text-gray-400">Assessment</th>
                <th className="px-4 py-3 font-medium text-left text-gray-500 dark:text-gray-400">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 dark:divide-gray-700/10">
              {models.map(model => {
                const res = results[model.id];
                if (!res) return (
                  <tr key={model.id} className="text-gray-400">
                    <td className="px-4 py-3">{model.name}</td>
                    <td className="px-4 py-3">—</td>
                    <td className="px-4 py-3">—</td>
                    <td className="px-4 py-3"><GlassBadge>Pending</GlassBadge></td>
                  </tr>
                );
                if (res.error) return (
                  <tr key={model.id}>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{model.name}</td>
                    <td className="px-4 py-3 text-rose-500 text-xs truncate max-w-[200px]">{res.error}</td>
                    <td className="px-4 py-3">—</td>
                    <td className="px-4 py-3"><GlassBadge variant="danger">Error</GlassBadge></td>
                  </tr>
                );
                const fmt = model.formatResult(res.raw || {});
                const interp = fmt.interpret(fmt.value);
                return (
                  <tr key={model.id}>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{model.name}</td>
                    <td className="px-4 py-3 font-mono text-gray-900 dark:text-white">
                      {typeof fmt.value === 'number' ? fmt.value.toFixed(3) : String(fmt.value)}
                      {fmt.unit && <span className="ml-1 text-gray-400">{fmt.unit}</span>}
                    </td>
                    <td className="px-4 py-3">
                      <GlassBadge variant={
                        interp.color === 'emerald' ? 'success' :
                        interp.color === 'rose' ? 'danger' :
                        interp.color === 'amber' ? 'warning' : 'primary'
                      }>
                        {interp.text}
                      </GlassBadge>
                    </td>
                    <td className="px-4 py-3">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </GlassPanel>
    </motion.div>
  );
};

export default LabBench;
