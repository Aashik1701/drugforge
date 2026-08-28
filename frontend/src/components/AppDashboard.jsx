import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  Search, Activity, Zap, Clock, CheckCircle2,
  AlertCircle, Beaker, FlaskConical, Target, Shield,
  Pill, BarChart3, Microscope, Brain, ArrowRight
} from 'lucide-react';
import GlassCard, { GlassPanel, GlassButton, GlassBadge } from './ui/GlassCard';
import { ShimmerCard } from './ui/ShimmerLoader';
import { useModelHealth } from '../hooks/useModelHealth';
import ComputeControl from './ComputeControl';

// ─── Model Registry ──────────────────────────────────────────
const MODEL_REGISTRY = [
  { id: 'solubility', name: 'Solubility', icon: FlaskConical, endpoint: '/predict/solubility' },
  { id: 'bbbp', name: 'BBBP', icon: Shield, endpoint: '/predict/bbbp' },
  { id: 'toxicity', name: 'Toxicity', icon: AlertCircle, endpoint: '/predict/toxicity' },
  { id: 'cyp3a4', name: 'CYP3A4', icon: Pill, endpoint: '/predict/cyp3a4' },
  { id: 'half-life', name: 'Half-Life', icon: Clock, endpoint: '/predict/half-life' },
  { id: 'cox2', name: 'COX-2', icon: Target, endpoint: '/predict/cox2' },
  { id: 'hepg2', name: 'HepG2', icon: Microscope, endpoint: '/predict/hepg2' },
  { id: 'ace2', name: 'ACE2', icon: Brain, endpoint: '/predict/ace2' },
  { id: 'binding-score', name: 'Binding Score', icon: BarChart3, endpoint: '/predict/binding-score' },
];

const AppDashboard = () => {
  const navigate = useNavigate();
  const [omniboxValue, setOmniboxValue] = useState('');
  const [recentMolecules, setRecentMolecules] = useState([]);

  const { data: modelHealth, isLoading: loadingHealth } = useModelHealth();

  // Load recent molecules from localStorage
  useEffect(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('drugforge_recent') || '[]');
      setRecentMolecules(stored.slice(0, 6));
    } catch {
      setRecentMolecules([]);
    }
  }, []);

  const handleOmniboxSubmit = useCallback((e) => {
    e.preventDefault();
    const q = omniboxValue.trim();
    if (!q) return;
    navigate(`/app/analyze?smiles=${encodeURIComponent(q)}`);
  }, [omniboxValue, navigate]);

  const handleRecentClick = useCallback((smiles) => {
    navigate(`/app/analyze?smiles=${encodeURIComponent(smiles)}`);
  }, [navigate]);

  // Compute model status indicators
  // API returns { "solubility": { status: "ready" }, "half_life": ... }
  // Frontend model IDs use hyphens (half-life), API uses underscores (half_life)
  const normalizeId = (id) => id.replace(/-/g, '_');
  const loadedModels = modelHealth?.models
    ? Object.entries(modelHealth.models).filter(([, v]) => v === true || v?.loaded === true || v?.status === 'ready')
    : [];
  const totalModels = MODEL_REGISTRY.length;
  const onlineCount = loadedModels.length;

  return (
    <div className="min-h-screen p-4 md:p-8 pb-24">
      <div className="max-w-6xl mx-auto space-y-8">

        {/* ─── Greeting ─────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="pt-8"
        >
          <h1 className="text-4xl md:text-5xl font-thin tracking-tight text-gray-800 dark:text-gray-100">
            Welcome to your{' '}
            <span className="bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">
              Lab
            </span>
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            Paste a molecule below to start analyzing, or pick a recent one.
          </p>
        </motion.div>

        {/* ─── Omnibox (Hero Element) ──────────────────────── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
        >
          <GlassPanel className="p-6 md:p-10">
            <form onSubmit={handleOmniboxSubmit} className="relative max-w-3xl mx-auto">
              <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                value={omniboxValue}
                onChange={(e) => setOmniboxValue(e.target.value)}
                placeholder="Enter SMILES, chemical name, or CID…"
                className="w-full h-16 pl-14 pr-36 rounded-2xl
                  bg-white/30 dark:bg-black/30
                  backdrop-blur-md
                  border border-white/30 dark:border-gray-700/30
                  text-gray-900 dark:text-gray-100 text-lg font-mono
                  placeholder-gray-400 dark:placeholder-gray-500
                  focus:outline-none focus:ring-2 focus:ring-cyan-500/50
                  transition-all duration-200"
                autoFocus
              />
              <button
                type="submit"
                className="absolute right-2 top-1/2 -translate-y-1/2
                  h-12 px-8 rounded-xl
                  bg-gradient-to-r from-cyan-500 to-violet-500
                  text-white font-medium
                  hover:shadow-glow-cyan active:scale-95
                  transition-all duration-200
                  flex items-center gap-2"
              >
                Analyze
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          </GlassPanel>
        </motion.div>

        {/* ─── System HUD + Recent Grid ────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

          {/* System HUD */}
          <GlassCard className="p-6 lg:col-span-1" hoverable={false}>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
              System Status
            </h3>

            {loadingHealth ? (
              <div className="space-y-4">
                <div className="h-4 w-full bg-white/10 rounded animate-shimmer" />
                <div className="h-4 w-3/4 bg-white/10 rounded animate-shimmer" />
              </div>
            ) : (
              <div className="space-y-5">
                {/* API Status */}
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${
                    modelHealth ? 'bg-emerald-500 shadow-lg shadow-emerald-500/40' : 'bg-rose-500 shadow-lg shadow-rose-500/40'
                  }`} />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    API {modelHealth ? 'Online' : 'Offline'}
                  </span>
                </div>

                {/* Models Online */}
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-500 dark:text-gray-400">Models</span>
                    <span className="font-mono text-cyan-500">{onlineCount}/{totalModels}</span>
                  </div>
                  <div className="h-2 bg-white/10 dark:bg-black/20 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-cyan-500 to-violet-500 rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${(onlineCount / totalModels) * 100}%` }}
                      transition={{ duration: 1, delay: 0.3 }}
                    />
                  </div>
                </div>

                {/* Per-model dots */}
                <div className="grid grid-cols-3 gap-2">
                  {MODEL_REGISTRY.map((model) => {
                    const apiId = normalizeId(model.id);
                    const entry = modelHealth?.models?.[model.id] || modelHealth?.models?.[apiId];
                    const isOnline = entry === true || entry?.loaded === true || entry?.status === 'ready';
                    return (
                      <div key={model.id} className="flex items-center gap-1.5" title={model.name}>
                        <div className={`w-2 h-2 rounded-full ${
                          isOnline
                            ? 'bg-emerald-500'
                            : 'bg-gray-400 dark:bg-gray-600'
                        }`} />
                        <span className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          {model.name}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </GlassCard>

          {/* Recent Activity - Masonry Glass Tiles */}
          <div className="lg:col-span-3">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
              Recent Molecules
            </h3>
            {recentMolecules.length === 0 ? (
              <GlassPanel className="flex flex-col items-center justify-center py-16 text-center">
                <Beaker className="w-12 h-12 text-gray-400 dark:text-gray-500 mb-4" />
                <p className="text-gray-500 dark:text-gray-400 mb-2">No recent analyses yet</p>
                <p className="text-sm text-gray-400 dark:text-gray-500">
                  Use the search bar above to analyze your first molecule.
                </p>
              </GlassPanel>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {recentMolecules.map((mol, i) => (
                  <motion.div
                    key={mol.smiles || i}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.08 }}
                  >
                    <GlassCard
                      className="p-5 cursor-pointer"
                      onClick={() => handleRecentClick(mol.smiles)}
                    >
                      <code className="text-sm font-mono text-gray-700 dark:text-gray-300 block truncate mb-2">
                        {mol.smiles}
                      </code>
                      <div className="flex items-center justify-between">
                        <GlassBadge variant="primary">{mol.type || 'Prediction'}</GlassBadge>
                        <span className="text-xs text-gray-400">{mol.time || ''}</span>
                      </div>
                    </GlassCard>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ─── Quick Actions Row ───────────────────────────── */}
        <div>
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
            Quick Actions
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Lab Bench', desc: 'Analyze a molecule', path: '/app/analyze', icon: FlaskConical, color: 'cyan' },
              { label: 'Batch Process', desc: 'Upload CSV', path: '/app/batch', icon: BarChart3, color: 'violet' },
              { label: 'Settings', desc: 'Account & prefs', path: '/app/settings', icon: Zap, color: 'amber' },
              { label: 'Molecular Viewer', desc: '3D visualization', path: '/molecular-visualization', icon: Microscope, color: 'emerald' },
            ].map((action, i) => (
              <motion.div
                key={action.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.08 }}
                whileHover={{ y: -4 }}
                onClick={() => navigate(action.path)}
                className="cursor-pointer"
              >
                <GlassCard className="p-5">
                  <action.icon className={`w-7 h-7 mb-3 text-${action.color}-500`} />
                  <h4 className="font-medium text-gray-800 dark:text-gray-200 text-sm">
                    {action.label}
                  </h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {action.desc}
                  </p>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        </div>

        {/* ─── Compute Control ─────────────────────────────── */}
        <div>
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
            System
          </h3>
          <ComputeControl />
        </div>
      </div>
    </div>
  );
};

export default AppDashboard;
