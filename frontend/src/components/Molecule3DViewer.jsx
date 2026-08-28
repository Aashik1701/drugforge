/**
 * Molecule3DViewer – WebGL-powered 3D molecular visualization & analysis.
 *
 * Uses a static import of 3Dmol.js and a single container div.
 * Features:
 *   - View-mode toggles (stick/sphere/line)
 *   - Spin play/pause, screenshot, reset
 *   - Electrostatic surface (Gasteiger charges, Red-White-Blue)
 *   - Pharmacophore markers (Donor/Acceptor/Aromatic spheres)
 *   - Interactive distance measurement (click two atoms)
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as $3Dmol from '3dmol/build/3Dmol.js';
import {
  Loader2,
  AlertTriangle,
  Box,
  Circle,
  Minus,
  Camera,
  RefreshCw,
  Layers,
  Pause,
  Play,
  Zap,
  Magnet,
  Ruler,
} from 'lucide-react';

/* -- tiny toolbar button -------------------------------------------------- */
const ControlButton = ({ icon: Icon, label, active, onClick }) => (
  <button
    onClick={onClick}
    title={label}
    className={`p-1.5 rounded-lg transition-all duration-200 ${
      active
        ? 'bg-cyan-500/30 text-cyan-300 shadow-[0_0_8px_rgba(34,211,238,0.3)]'
        : 'text-slate-400 hover:text-white hover:bg-white/10'
    }`}
  >
    <Icon className="w-4 h-4" />
  </button>
);

/* -- science toolbar button (right side, vertical) ------------------------ */
const ScienceButton = ({ icon: Icon, label, active, onClick, activeColor }) => (
  <button
    onClick={onClick}
    title={label}
    className={`p-2.5 rounded-xl backdrop-blur-md border transition-all duration-200 group relative ${
      active
        ? 'bg-white/10 border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.3)]'
        : 'bg-black/20 border-white/10 hover:bg-white/10'
    }`}
  >
    <Icon className={`w-4 h-4 ${active ? activeColor : 'text-slate-300'}`} />
    <span className="absolute px-2 py-1 mr-3 text-xs text-white transition-opacity -translate-y-1/2 rounded opacity-0 pointer-events-none right-full top-1/2 bg-black/80 group-hover:opacity-100 whitespace-nowrap">
      {label}
    </span>
  </button>
);

/* -- main component ------------------------------------------------------- */
const Molecule3DViewer = ({
  smiles,
  width = 400,
  height = 300,
  showControls = true,
  spin = true,
}) => {
  const viewerRef = useRef(null);
  const viewerInstance = useRef(null);
  const molBlockRef = useRef(null);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('stick');
  const [showSurface, setShowSurface] = useState(false);
  const [hoveredAtom, setHoveredAtom] = useState(null);
  const [isSpinning, setIsSpinning] = useState(spin);

  /* -- science layer states ----------------------------------------------- */
  const [molData, setMolData] = useState(null);
  const [showElectrostatics, setShowElectrostatics] = useState(false);
  const [showPharmacophores, setShowPharmacophores] = useState(false);
  const [measureMode, setMeasureMode] = useState(false);
  const measureAtomRef = useRef(null);
  const [measurement, setMeasurement] = useState(null);

  /* -- style map ---------------------------------------------------------- */
  const styleForMode = useCallback((mode) => {
    switch (mode) {
      case 'sphere':
        return { sphere: { scale: 0.4, colorscheme: 'Jmol' } };
      case 'line':
        return { line: { colorscheme: 'Jmol' } };
      case 'stick':
      default:
        return {
          stick: { radius: 0.15, colorscheme: 'Jmol' },
          sphere: { scale: 0.25, colorscheme: 'Jmol' },
        };
    }
  }, []);

  /* -- apply style (non-science surfaces) --------------------------------- */
  const applyStyle = useCallback(() => {
    const viewer = viewerInstance.current;
    if (!viewer) return;

    viewer.setStyle({}, styleForMode(viewMode));
    viewer.removeAllSurfaces();

    if (showSurface && !showElectrostatics) {
      viewer.addSurface($3Dmol.SurfaceType.VDW, {
        opacity: 0.25,
        color: 'white',
      });
    }

    viewer.render();
  }, [viewMode, showSurface, showElectrostatics, styleForMode]);

  /* re-apply style when viewMode / showSurface change */
  useEffect(() => {
    applyStyle();
  }, [applyStyle]);

  /* -- resize observer: auto-resize 3Dmol canvas when container changes --- */
  useEffect(() => {
    const el = viewerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      if (viewerInstance.current) {
        try { viewerInstance.current.resize(); viewerInstance.current.render(); } catch (_) { /* ok */ }
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /* -- fetch 3-D coords + charges + features ------------------------------ */
  useEffect(() => {
    if (!smiles || !smiles.trim()) return;
    let isMounted = true;

    const fetchAndRender3D = async () => {
      setIsLoading(true);
      setError(null);
      setShowElectrostatics(false);
      setShowPharmacophores(false);
      setMeasureMode(false);
      setMeasurement(null);
      measureAtomRef.current = null;

      try {
        const API_URL =
          import.meta.env.VITE_API_URL || 'http://localhost:5001';
        const trimmedSmiles = smiles.trim();
        const res = await fetch(`${API_URL}/utils/generate-3d`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ smiles: trimmedSmiles }),
        });

        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.error || errBody.detail || `Server error ${res.status}`);
        }

        const data = await res.json();
        if (!isMounted) return;
        molBlockRef.current = data.mol_block;

        /* ---- initialise or re-use viewer ---- */
        if (viewerInstance.current) {
          // Viewer already exists – just re-use it
          try { viewerInstance.current.resize(); } catch (_) { /* ok */ }
        }

        if (!viewerInstance.current && viewerRef.current) {
          // Force explicit pixel dimensions BEFORE creating viewer to avoid zero-size WebGL canvas
          // When width/height are percentages, they may not have computed yet
          const forceValidDimensions = async () => {
            for (let attempt = 0; attempt < 5; attempt++) {
              await new Promise((r) => requestAnimationFrame(r));
              
              let rect = viewerRef.current.getBoundingClientRect();

              
              if (rect.width > 0 && rect.height > 0) {
                // Good! Dimensions are valid, set them explicitly
                const el = viewerRef.current;
                el.style.width = rect.width + 'px';
                el.style.height = rect.height + 'px';

                return true;
              }
              
              // Still zero, try to compute from parameter dimensions
              if (attempt === 2) {
                const pxW = typeof width === 'number' ? width : 400;
                const pxH = typeof height === 'number' ? height : 300;
                viewerRef.current.style.width = pxW + 'px';
                viewerRef.current.style.height = pxH + 'px';

              }
              
              await new Promise((r) => setTimeout(r, 100));
            }
          };
          
          await forceValidDimensions();
          
          if (!isMounted) return;
          const finalRect = viewerRef.current.getBoundingClientRect();
          if (finalRect.width === 0 || finalRect.height === 0) {
            console.error('[3DViewer] Container still has zero dimensions:', finalRect);
            throw new Error('Container has zero dimensions - cannot create WebGL viewer');
          }

          viewerInstance.current = $3Dmol.createViewer(viewerRef.current, {
            backgroundColor: '#111827',
          });

        }

        const viewer = viewerInstance.current;
        if (!viewer) throw new Error('Viewer failed to initialize');

        viewer.clear();
        viewer.removeAllSurfaces();
        viewer.removeAllShapes();
        viewer.removeAllLabels();
        viewer.addModel(data.mol_block, 'sdf');

        // Attach Gasteiger charges to atoms for electrostatic colouring
        if (data.charges) {
          try {
            const atoms = viewer.getModel().selectedAtoms({});
            if (atoms.length === data.charges.length) {
              atoms.forEach((atom, i) => {
                if (!atom.properties) atom.properties = {};
                atom.properties.charge = data.charges[i];
              });
            }
          } catch (_) {
            /* charges unavailable */
          }
        }

        /* atom hover labels (now include partial charge) */
        viewer.setHoverable(
          {},
          true,
          (atom) => {
            if (!isMounted) return;
            const charge = atom.properties?.charge;
            setHoveredAtom({
              elem: atom.elem,
              serial: atom.serial,
              x: atom.x?.toFixed(2),
              y: atom.y?.toFixed(2),
              z: atom.z?.toFixed(2),
              charge: charge != null ? charge.toFixed(3) : null,
            });
            const lbl =
              charge != null
                ? `${atom.elem} (${charge >= 0 ? '+' : ''}${charge.toFixed(2)})`
                : atom.elem;
            viewer.addLabel(lbl, {
              position: atom,
              backgroundColor: 'rgba(0,0,0,0.7)',
              fontColor: 'white',
              fontSize: 12,
              borderRadius: 4,
            });
            viewer.render();
          },
          (atom) => {
            if (!isMounted) return;
            setHoveredAtom(null);
            viewer.removeAllLabels();
            viewer.render();
          },
        );

        viewer.setStyle({}, styleForMode(viewMode));
        viewer.resize();
        viewer.zoomTo();
        viewer.render();
        if (spin) {
          viewer.spin('y', 0.5);
          setIsSpinning(true);
        }

        // Set molData AFTER viewer is rendered to avoid mid-creation re-renders
        if (isMounted) setMolData(data);
      } catch (err) {
        console.error('[3DViewer] Error:', err);
        if (isMounted) setError('Could not generate 3D structure');
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchAndRender3D();

    return () => {
      isMounted = false;
      if (viewerInstance.current) {
        try {
          viewerInstance.current.spin(false);
          viewerInstance.current.clear();
        } catch (_) { /* ok */ }
        viewerInstance.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smiles]);

  /* -- science layers effect ---------------------------------------------- */
  useEffect(() => {
    const viewer = viewerInstance.current;
    if (!viewer || !molData) return;

    viewer.removeAllShapes();
    viewer.removeAllSurfaces();

    // Re-apply plain surface if on and ESP is off
    if (showSurface && !showElectrostatics) {
      viewer.addSurface($3Dmol.SurfaceType.VDW, {
        opacity: 0.25,
        color: 'white',
      });
    }

    // A. Electrostatic surface (Red-White-Blue)
    if (showElectrostatics && molData.charges?.length) {
      viewer.addSurface($3Dmol.SurfaceType.VDW, {
        opacity: 0.6,
        colorscheme: {
          prop: 'charge',
          gradient: 'rwb',
          min: -0.5,
          max: 0.5,
        },
      });
    }

    // B. Pharmacophore spheres
    if (showPharmacophores && molData.features?.length) {
      molData.features.forEach((feat) => {
        let color = 'gray';
        if (feat.family === 'Donor') color = '#00ff00';
        if (feat.family === 'Acceptor') color = '#a020f0';
        if (feat.family === 'Aromatic') color = '#ffa500';

        viewer.addSphere({
          center: { x: feat.x, y: feat.y, z: feat.z },
          radius: 1.0,
          color,
          alpha: 0.4,
        });
      });
    }

    // C. Measurement mode
    if (measureMode) {
      viewer.setClickable({}, true, (atom) => {
        const first = measureAtomRef.current;
        if (!first) {
          measureAtomRef.current = atom;
          viewer.addSphere({
            center: { x: atom.x, y: atom.y, z: atom.z },
            radius: 0.35,
            color: '#facc15',
            alpha: 0.8,
          });
          viewer.addLabel(`${atom.elem}${atom.serial}`, {
            position: atom,
            backgroundColor: '#facc15',
            fontColor: 'black',
            fontSize: 11,
            borderRadius: 4,
          });
          viewer.render();
        } else {
          const dx = atom.x - first.x;
          const dy = atom.y - first.y;
          const dz = atom.z - first.z;
          const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

          viewer.addCylinder({
            start: { x: first.x, y: first.y, z: first.z },
            end: { x: atom.x, y: atom.y, z: atom.z },
            radius: 0.05,
            color: '#facc15',
            fromCap: true,
            toCap: true,
          });

          viewer.addLabel(`${dist.toFixed(2)} \u00C5`, {
            position: {
              x: (first.x + atom.x) / 2,
              y: (first.y + atom.y) / 2,
              z: (first.z + atom.z) / 2,
            },
            backgroundColor: 'rgba(0,0,0,0.8)',
            fontColor: '#facc15',
            fontSize: 13,
            borderRadius: 4,
          });

          viewer.addSphere({
            center: { x: atom.x, y: atom.y, z: atom.z },
            radius: 0.35,
            color: '#facc15',
            alpha: 0.8,
          });

          setMeasurement({
            dist: dist.toFixed(2),
            a1: `${first.elem}${first.serial}`,
            a2: `${atom.elem}${atom.serial}`,
          });

          viewer.render();
          measureAtomRef.current = null;
        }
      });
    } else {
      viewer.setClickable({}, false);
      setMeasurement(null);
      measureAtomRef.current = null;
    }

    viewer.render();
  }, [showElectrostatics, showPharmacophores, measureMode, molData, showSurface]);

  /* -- science toggles ---------------------------------------------------- */
  const toggleElectrostatics = useCallback(() => {
    setShowElectrostatics((p) => !p);
    if (!showElectrostatics) setShowSurface(false);
  }, [showElectrostatics]);

  const togglePharmacophores = useCallback(() => {
    setShowPharmacophores((p) => !p);
  }, []);

  const toggleMeasure = useCallback(() => {
    setMeasureMode((p) => !p);
  }, []);

  /* -- screenshot --------------------------------------------------------- */
  const handleScreenshot = useCallback(() => {
    const viewer = viewerInstance.current;
    if (!viewer) return;
    const png = viewer.pngURI();
    const a = document.createElement('a');
    a.href = png;
    a.download = `molecule-${smiles?.slice(0, 12) || 'capture'}.png`;
    a.click();
  }, [smiles]);

  /* -- spin toggle -------------------------------------------------------- */
  const handleToggleSpin = useCallback(() => {
    const viewer = viewerInstance.current;
    if (!viewer) return;
    if (isSpinning) {
      viewer.spin(false);
      setIsSpinning(false);
    } else {
      viewer.spin('y', 0.5);
      setIsSpinning(true);
    }
  }, [isSpinning]);

  /* -- reset camera ------------------------------------------------------- */
  const handleReset = useCallback(() => {
    const viewer = viewerInstance.current;
    if (!viewer) return;
    viewer.zoomTo();
    viewer.render();
    if (isSpinning) viewer.spin('y', 0.5);
  }, [isSpinning]);

  /* -- dimensions --------------------------------------------------------- */
  const cssWidth = typeof width === 'number' ? `${width}px` : width;
  const cssHeight = typeof height === 'number' ? `${height}px` : height;

  const hasScienceData =
    molData?.charges?.length > 0 || molData?.features?.length > 0;

  return (
    <div className="relative" style={{ width: cssWidth, height: cssHeight, display: 'flex' }}>
      {/* WebGL canvas target — fill parent container */}
      <div
        ref={viewerRef}
        className={`flex-1 rounded-xl border border-white/10 shadow-inner ${
          measureMode ? 'cursor-crosshair' : 'cursor-move'
        }`}
        style={{ position: 'relative', backgroundColor: '#111827', minWidth: 0, minHeight: 0 }}
      />

      {/* -- Bottom Glass Toolbar ------------------------------------------ */}
      {showControls && !isLoading && !error && smiles && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 px-2 py-1.5 rounded-xl bg-black/40 backdrop-blur-md border border-white/10 shadow-lg">
          <ControlButton icon={Box} label="Stick" active={viewMode === 'stick'} onClick={() => setViewMode('stick')} />
          <ControlButton icon={Circle} label="Sphere" active={viewMode === 'sphere'} onClick={() => setViewMode('sphere')} />
          <ControlButton icon={Minus} label="Line" active={viewMode === 'line'} onClick={() => setViewMode('line')} />
          <div className="w-px h-5 mx-1 bg-white/20" />
          <ControlButton icon={Layers} label="Surface" active={showSurface} onClick={() => setShowSurface((p) => !p)} />
          <ControlButton icon={isSpinning ? Pause : Play} label={isSpinning ? 'Stop Spin' : 'Start Spin'} active={isSpinning} onClick={handleToggleSpin} />
          <ControlButton icon={Camera} label="Screenshot" active={false} onClick={handleScreenshot} />
          <ControlButton icon={RefreshCw} label="Reset View" active={false} onClick={handleReset} />
        </div>
      )}

      {/* -- Right Science Toolbar ----------------------------------------- */}
      {showControls && !isLoading && !error && smiles && hasScienceData && (
        <div className="absolute z-30 flex flex-col gap-2 top-4 right-4">
          <ScienceButton icon={Zap} label="Electrostatics" active={showElectrostatics} onClick={toggleElectrostatics} activeColor="text-rose-400" />
          <ScienceButton icon={Magnet} label="Pharmacophores" active={showPharmacophores} onClick={togglePharmacophores} activeColor="text-emerald-400" />
          <ScienceButton icon={Ruler} label="Measure Distance" active={measureMode} onClick={toggleMeasure} activeColor="text-amber-400" />
        </div>
      )}

      {/* -- Electrostatic Legend ------------------------------------------- */}
      {showElectrostatics && showControls && (
        <div className="absolute z-30 p-3 text-xs text-white border bottom-14 left-4 bg-black/60 backdrop-blur-md rounded-xl border-white/10">
          <div className="mb-2 font-bold">Surface Charge (ESP)</div>
          <div className="w-24 h-2 rounded-full bg-gradient-to-r from-red-500 via-white to-blue-500" />
          <div className="flex justify-between mt-1 text-[10px] text-slate-300">
            <span>{"\u03B4"}&minus; Neg</span>
            <span>{"\u03B4"}+ Pos</span>
          </div>
        </div>
      )}

      {/* -- Pharmacophore Legend ------------------------------------------- */}
      {showPharmacophores && showControls && (
        <div className="absolute z-30 p-3 text-xs text-white border bottom-14 left-4 bg-black/60 backdrop-blur-md rounded-xl border-white/10">
          <div className="mb-2 font-bold">Binding Features</div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center"><span className="w-2 h-2 mr-2 bg-green-500 rounded-full" /> H-Bond Donor</div>
            <div className="flex items-center"><span className="w-2 h-2 mr-2 bg-purple-500 rounded-full" /> H-Bond Acceptor</div>
            <div className="flex items-center"><span className="w-2 h-2 mr-2 bg-orange-500 rounded-full" /> Aromatic Ring</div>
          </div>
        </div>
      )}

      {/* -- Measurement HUD ----------------------------------------------- */}
      {measureMode && showControls && (
        <div className="absolute z-30 px-3 py-2 text-xs text-white border top-4 left-4 bg-black/60 backdrop-blur-md rounded-xl border-amber-500/30">
          <div className="flex items-center gap-1 mb-1 font-bold text-amber-400">
            <Ruler className="w-3 h-3" /> Measure Mode
          </div>
          {measurement ? (
            <div className="font-mono">
              {measurement.a1} &rarr; {measurement.a2}:{' '}
              <span className="font-bold text-amber-300">{measurement.dist} &#x212B;</span>
            </div>
          ) : (
            <div className="text-slate-400">Click two atoms to measure</div>
          )}
        </div>
      )}

      {/* -- Hover Atom Info ------------------------------------------------ */}
      {hoveredAtom && showControls && !measureMode && (
        <div className="absolute top-3 right-3 z-30 px-3 py-1.5 rounded-lg bg-black/50 backdrop-blur-md border border-white/10 text-xs text-slate-200 font-mono">
          {hoveredAtom.elem} #{hoveredAtom.serial}
          {hoveredAtom.charge != null && (
            <span className={parseFloat(hoveredAtom.charge) >= 0 ? ' text-blue-400' : ' text-rose-400'}>
              {' '}({parseFloat(hoveredAtom.charge) >= 0 ? '+' : ''}{hoveredAtom.charge})
            </span>
          )}
          <span className="text-slate-500">
            {' '}({hoveredAtom.x}, {hoveredAtom.y}, {hoveredAtom.z})
          </span>
        </div>
      )}

      {/* -- Loading ------------------------------------------------------- */}
      {isLoading && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center rounded-xl"
          style={{ backgroundColor: 'rgba(0,0,0,0.3)', pointerEvents: 'none' }}
        >
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        </div>
      )}

      {/* -- Error --------------------------------------------------------- */}
      {error && !isLoading && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-4 text-sm text-center text-rose-400">
          <AlertTriangle className="w-6 h-6 mb-2 opacity-80" />
          <span>{error}</span>
        </div>
      )}

      {/* -- Empty --------------------------------------------------------- */}
      {!smiles && !isLoading && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">
          Waiting for molecule...
        </div>
      )}
    </div>
  );
};

export default Molecule3DViewer;
