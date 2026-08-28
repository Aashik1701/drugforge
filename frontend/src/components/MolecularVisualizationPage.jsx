import React, { useState, useCallback } from 'react';
import { Beaker, Search, RotateCcw, Atom, Sparkles } from 'lucide-react';
import Molecule3DViewer from './Molecule3DViewer';

const EXAMPLES = [
  { name: 'Aspirin', smiles: 'CC(=O)OC1=CC=CC=C1C(=O)O' },
  { name: 'Caffeine', smiles: 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C' },
  { name: 'Ibuprofen', smiles: 'CC(C)CC1=CC=C(C=C1)C(C)C(=O)O' },
  { name: 'Paracetamol', smiles: 'CC(=O)NC1=CC=C(C=C1)O' },
  { name: 'Penicillin G', smiles: 'CC1([C@@H](N2[C@H](S1)[C@@H](C2=O)NC(=O)CC3=CC=CC=C3)C(=O)O)C' },
  { name: 'Morphine', smiles: 'CN1CC[C@]23C4=C5C(=C(C=C4)O)O[C@H]2[C@@H](C=C3)[C@H]1C5' },
  { name: 'Warfarin', smiles: 'CC(=O)CC(C1=CC=CC=C1)C2=C(C3=CC=CC=C3OC2=O)O' },
  { name: 'Metformin', smiles: 'CN(C)C(=N)NC(=N)N' },
];

/**
 * Molecule Studio – full-page immersive 3D molecular visualization.
 *
 * Horizontal "Quick Select" glass chips replace the vertical sidebar,
 * giving the 3D viewer 100% width.
 */
const MolecularVisualizationPage = () => {
  const [inputValue, setInputValue] = useState(EXAMPLES[0].smiles);
  const [currentSmiles, setCurrentSmiles] = useState(EXAMPLES[0].smiles);
  const [currentName, setCurrentName] = useState(EXAMPLES[0].name);

  const handleSubmit = useCallback(
    (e) => {
      e?.preventDefault();
      const trimmed = inputValue.trim();
      if (trimmed) {
        setCurrentSmiles(trimmed);
        setCurrentName('Custom');
      }
    },
    [inputValue],
  );

  const handleExample = useCallback((ex) => {
    setInputValue(ex.smiles);
    setCurrentSmiles(ex.smiles);
    setCurrentName(ex.name);
  }, []);

  const handleClear = useCallback(() => {
    setInputValue('');
    setCurrentSmiles('');
    setCurrentName('');
  }, []);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* ── Header + Search ────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500/20 to-violet-500/20 border border-white/10">
            <Atom className="w-6 h-6 text-cyan-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400">
              Molecule Studio
            </h1>
            <p className="text-xs text-slate-400">
              Interactive 3D visualization engine
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="relative w-full md:w-96 flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Enter SMILES…"
              className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-white/10 border border-white/20 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 backdrop-blur-md font-mono"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-sm font-medium hover:bg-cyan-500/30 transition-colors"
          >
            Visualize
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="p-2 rounded-xl bg-white/5 border border-white/10 text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            title="Clear"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* ── Quick Select Chips ─────────────────────────────────── */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-hide">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider mr-1 flex items-center shrink-0">
          <Sparkles className="w-3 h-3 mr-1" /> Quick Load:
        </span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.name}
            onClick={() => handleExample(ex)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all border ${
              currentSmiles === ex.smiles
                ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                : 'bg-white/5 border-white/10 text-slate-500 hover:bg-white/10 hover:text-slate-300'
            }`}
          >
            {ex.name}
          </button>
        ))}
      </div>

      {/* ── Molecule label ─────────────────────────────────────── */}
      {currentName && currentSmiles && (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white">{currentName}</span>
          <span className="text-xs font-mono text-slate-500 truncate max-w-sm">
            {currentSmiles}
          </span>
        </div>
      )}

      {/* ── 3D Viewer – Full Width ─────────────────────────────── */}
      <div className="flex-1 relative rounded-2xl overflow-hidden shadow-2xl border border-white/20 min-h-[400px]">
        {currentSmiles ? (
          <Molecule3DViewer
            smiles={currentSmiles}
            width="100%"
            height="100%"
            showControls={true}
            spin={true}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-3 bg-[#0a0f1a]">
            <Beaker className="w-12 h-12 opacity-40" />
            <p className="text-sm">
              Enter a SMILES string or pick an example to begin
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default MolecularVisualizationPage;
