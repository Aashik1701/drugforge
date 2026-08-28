import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as $3Dmol from '3dmol/build/3Dmol.js';
import { AlertTriangle, Loader2 } from 'lucide-react';

const PROTEIN_STYLES = [
  { key: 'cartoon', label: 'Cartoon' },
  { key: 'surface', label: 'Surface' },
  { key: 'line', label: 'Line' },
];

const LIGAND_STYLES = [
  { key: 'stick', label: 'Stick' },
  { key: 'sphere', label: 'Sphere' },
];

const DockingPoseViewer = ({ receptorPdbqt, ligandPdbqt, height = 420 }) => {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const [error, setError] = useState('');
  const [proteinStyle, setProteinStyle] = useState('cartoon');
  const [ligandStyle, setLigandStyle] = useState('stick');

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    viewerRef.current = $3Dmol.createViewer(containerRef.current, {
      backgroundColor: '#0f172a',
    });

    const observer = new ResizeObserver(() => {
      if (viewerRef.current) {
        try {
          viewerRef.current.resize();
          viewerRef.current.render();
        } catch (_) {
          // ignore resize errors
        }
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      if (viewerRef.current) {
        try {
          viewerRef.current.spin(false);
          viewerRef.current.clear();
        } catch (_) {
          // ignore cleanup errors
        }
      }
      viewerRef.current = null;
    };
  }, []);

  const applyStyles = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || !receptorPdbqt || !ligandPdbqt) return;

    try {
      // --- Protein style ---
      const proteinSpec = {};
      if (proteinStyle === 'cartoon') {
        proteinSpec.cartoon = { color: '#94a3b8', opacity: 0.55 };
        proteinSpec.line = { color: '#9ca3af', opacity: 0.25 };
      } else if (proteinStyle === 'surface') {
        proteinSpec.cartoon = { color: '#94a3b8', opacity: 0.2 };
      } else if (proteinStyle === 'line') {
        proteinSpec.line = { color: '#9ca3af', opacity: 0.55 };
      }
      viewer.setStyle({ model: 0 }, proteinSpec);

      // Add surface separately for surface mode
      viewer.removeAllSurfaces();
      if (proteinStyle === 'surface') {
        viewer.addSurface($3Dmol.SurfaceType.VDW, {
          opacity: 0.45,
          color: '#64748b',
        }, { model: 0 });
      }

      // --- Ligand style ---
      const ligandSpec = {};
      if (ligandStyle === 'stick') {
        ligandSpec.stick = { radius: 0.2, colorscheme: 'Jmol' };
        ligandSpec.sphere = { scale: 0.28, colorscheme: 'Jmol' };
      } else if (ligandStyle === 'sphere') {
        ligandSpec.sphere = { scale: 0.6, colorscheme: 'Jmol' };
      }
      viewer.setStyle({ model: 1 }, ligandSpec);

      viewer.render();
    } catch (err) {
      console.error('[DockingPoseViewer] style error', err);
    }
  }, [proteinStyle, ligandStyle, receptorPdbqt, ligandPdbqt]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    if (!receptorPdbqt || !ligandPdbqt) {
      viewer.clear();
      viewer.render();
      return;
    }

    try {
      setError('');
      viewer.clear();
      viewer.removeAllModels();
      viewer.removeAllSurfaces();

      // Detect format — support both PDB and PDBQT
      const receptorFormat =
        receptorPdbqt.includes('PDBQT') ||
        /\s[+-]?\d+\.\d+\s+[A-Z]{1,2}\s*$/.test(receptorPdbqt.split('\n')[3] || '')
          ? 'pdbqt'
          : 'pdb';

      viewer.addModel(receptorPdbqt, receptorFormat);
      viewer.addModel(ligandPdbqt, 'pdbqt');

      // Apply current styles
      applyStyles();

      viewer.zoomTo({ model: 1 });
      viewer.zoom(1.2, 900);
      viewer.spin('y', 0.3);
      viewer.render();
    } catch (err) {
      console.error('[DockingPoseViewer] render error', err);
      setError('Unable to render docking overlay');
    }
  }, [receptorPdbqt, ligandPdbqt]);

  // Re-apply styles when toggles change (without re-adding models)
  useEffect(() => {
    applyStyles();
  }, [applyStyles]);

  return (
    <div className="relative rounded-2xl overflow-hidden border border-white/20 bg-[#0f172a]" style={{ height }}>
      <div ref={containerRef} className="w-full h-full" />

      {/* Style toggles — only show when both models loaded */}
      {receptorPdbqt && ligandPdbqt && (
        <div className="absolute top-3 right-3 flex flex-col gap-2 z-10">
          {/* Protein style */}
          <div className="bg-black/60 backdrop-blur-sm rounded-lg px-2 py-1.5 flex items-center gap-1">
            <span className="text-[10px] text-slate-400 mr-1 uppercase tracking-wide">Protein</span>
            {PROTEIN_STYLES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setProteinStyle(key)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  proteinStyle === key
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-white/10'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {/* Ligand style */}
          <div className="bg-black/60 backdrop-blur-sm rounded-lg px-2 py-1.5 flex items-center gap-1">
            <span className="text-[10px] text-slate-400 mr-1 uppercase tracking-wide">Ligand</span>
            {LIGAND_STYLES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setLigandStyle(key)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  ligandStyle === key
                    ? 'bg-emerald-600 text-white'
                    : 'text-slate-300 hover:bg-white/10'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!receptorPdbqt || !ligandPdbqt ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          Preparing docking overlay...
        </div>
      ) : null}

      {error ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-sm text-rose-300 bg-black/40">
          <AlertTriangle className="w-5 h-5 mb-2" />
          {error}
        </div>
      ) : null}
    </div>
  );
};

export default DockingPoseViewer;
