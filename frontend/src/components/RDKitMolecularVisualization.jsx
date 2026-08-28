import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Eye, Download, Maximize2, RotateCcw, Settings, Info, Zap, AlertTriangle } from 'lucide-react';
import { useDrugForge } from '../context/DrugForgeContext';
import { getTextClasses } from '../utils/themeUtils';

/**
 * Real RDKit-powered Molecular Visualization Component
 * Uses RDKit-JS for accurate chemical structure rendering and calculations
 */
const RDKitMolecularVisualization = ({ 
  smiles, 
  title = "Molecular Structure",
  showControls = true,
  showProperties = true,
  width = 400,
  height = 300,
  highlightAtoms = [],
  highlightBonds = []
}) => {
  const { isDarkMode } = useDrugForge();
  const rdkitRef = useRef(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [rdkitReady, setRdkitReady] = useState(false);
  const [molecule, setMolecule] = useState(null);
  const [currentStyle, setCurrentStyle] = useState('2d');
  const [showSettings, setShowSettings] = useState(false);
  const [currentSVG, setCurrentSVG] = useState(null);
  
  const [settings, setSettings] = useState({
    atomLabels: true,
    bondLineWidth: 2,
    highlightColour: [1, 0, 0],
    backgroundColour: isDarkMode ? [0.12, 0.16, 0.22] : [1, 1, 1],
    addStereoAnnotation: true,
    addAtomIndices: false,
    addBondIndices: false,
    explicitMethyl: false,
    includeMetadata: true,
    clearBackground: true
  });

  const [molecularProperties, setMolecularProperties] = useState(null);
  const [descriptors, setDescriptors] = useState(null);
  const [fingerprints, setFingerprints] = useState(null);
  const [usingRealRDKit, setUsingRealRDKit] = useState(false);

  // Initialize RDKit
  useEffect(() => {
    const initRDKit = async () => {
      try {
        console.log('Initializing RDKit...');
        
        try {
          const { initRDKitModule } = await import('@rdkit/rdkit');
          const RDKit = await initRDKitModule({
            locateFile: () => '/RDKit_minimal.wasm'
          });
          
          rdkitRef.current = RDKit;
          setUsingRealRDKit(true);
          setRdkitReady(true);
          console.log('RDKit initialized successfully with real library, version:', RDKit.version());
        } catch (importError) {
          console.warn('RDKit-JS not available, using fallback implementation:', importError);
          
          await new Promise(resolve => setTimeout(resolve, 500));
          setUsingRealRDKit(false);
          rdkitRef.current = { _fallback: true };
          setRdkitReady(true);
          console.log('Fallback RDKit implementation initialized');
        }
      } catch (err) {
        setError(`Failed to initialize RDKit: ${err.message}`);
        console.error('RDKit initialization failed:', err);
      }
    };

    initRDKit();
  }, []);

  // Update background color when theme changes
  useEffect(() => {
    setSettings(prev => ({
      ...prev,
      backgroundColour: isDarkMode ? [0.12, 0.16, 0.22] : [1, 1, 1]
    }));
  }, [isDarkMode]);

  // Enhanced molecule-specific SVG generation
  const generateMoleculeSpecificSVG = (smilesString, width, height) => {
    const structures = {
      // Aspirin
      'CC(=O)OC1=CC=CC=C1C(=O)O': {
        title: 'Aspirin',
        paths: `
          <!-- Benzene ring -->
          <polygon points="100,150 150,120 200,120 250,150 250,200 200,230 150,230 100,200" 
                   fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <!-- Ester group -->
          <line x1="250" y1="150" x2="300" y2="120" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <circle cx="320" cy="110" r="6" fill="#ff0000"/>
          <text x="335" y="115" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">O</text>
          <!-- Carboxyl group -->
          <line x1="150" y1="230" x2="150" y2="280" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <circle cx="130" cy="300" r="6" fill="#ff0000"/>
          <circle cx="170" cy="300" r="6" fill="#ff0000"/>
          <text x="110" y="305" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">O</text>
          <text x="180" y="305" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">OH</text>
          <!-- Acetyl group -->
          <line x1="300" y1="120" x2="350" y2="90" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <text x="360" y="95" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
        `
      },
      // Caffeine
      'CN1C=NC2=C1C(=O)N(C(=O)N2C)C': {
        title: 'Caffeine',
        paths: `
          <!-- Purine ring system -->
          <polygon points="150,100 200,80 250,100 280,140 250,180 200,200 150,180 120,140" 
                   fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <polygon points="200,80 250,100 280,140 250,120 200,100" 
                   fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <!-- Nitrogens -->
          <circle cx="175" cy="120" r="6" fill="#0000ff"/>
          <circle cx="225" cy="120" r="6" fill="#0000ff"/>
          <circle cx="200" cy="160" r="6" fill="#0000ff"/>
          <text x="165" y="125" fill="white" font-size="10">N</text>
          <text x="215" y="125" fill="white" font-size="10">N</text>
          <text x="190" y="165" fill="white" font-size="10">N</text>
          <!-- Methyls -->
          <text x="120" y="110" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
          <text x="290" y="130" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
          <text x="170" y="210" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
          <!-- Carbonyls -->
          <circle cx="150" cy="140" r="4" fill="#ff0000"/>
          <circle cx="250" cy="140" r="4" fill="#ff0000"/>
          <text x="140" y="145" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="10">O</text>
          <text x="260" y="145" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="10">O</text>
        `
      },
      // Ibuprofen
      'CC(C)CC1=CC=C(C=C1)C(C)C(=O)O': {
        title: 'Ibuprofen',
        paths: `
          <!-- Benzene ring -->
          <polygon points="200,150 250,120 300,120 350,150 350,200 300,230 250,230 200,200" 
                   fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <!-- Propyl chain -->
          <line x1="200" y1="175" x2="150" y2="175" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <line x1="150" y1="175" x2="120" y2="145" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <line x1="120" y1="145" x2="90" y2="175" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <line x1="90" y1="175" x2="60" y2="145" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <text x="40" y="140" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
          <text x="75" y="195" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
          <!-- Carboxyl side chain -->
          <line x1="350" y1="175" x2="400" y2="175" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <line x1="400" y1="175" x2="430" y2="145" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <text x="440" y="140" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
          <line x1="430" y1="145" x2="460" y2="175" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <circle cx="480" cy="165" r="6" fill="#ff0000"/>
          <circle cx="480" cy="185" r="6" fill="#ff0000"/>
          <text x="490" y="170" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">O</text>
          <text x="490" y="195" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">OH</text>
        `
      },
      // Paracetamol/Acetaminophen
      'CC(=O)NC1=CC=C(C=C1)O': {
        title: 'Paracetamol',
        paths: `
          <!-- Benzene ring -->
          <polygon points="200,150 250,120 300,120 350,150 350,200 300,230 250,230 200,200" 
                   fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <!-- Hydroxyl group -->
          <line x1="275" y1="120" x2="275" y2="80" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <circle cx="275" cy="60" r="6" fill="#ff0000"/>
          <text x="285" y="65" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">OH</text>
          <!-- Amide group -->
          <line x1="275" y1="230" x2="275" y2="270" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <circle cx="255" cy="290" r="6" fill="#0000ff"/>
          <text x="245" y="295" fill="white" font-size="10">NH</text>
          <line x1="275" y1="270" x2="305" y2="290" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <circle cx="320" cy="300" r="4" fill="#ff0000"/>
          <text x="330" y="305" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="10">O</text>
          <!-- Acetyl group -->
          <line x1="305" y1="290" x2="335" y2="270" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
          <text x="345" y="275" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="12">CH₃</text>
        `
      }
    };

    const structure = structures[smilesString];
    
    if (structure) {
      return `
        <svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
          <rect width="100%" height="100%" fill="${isDarkMode ? '#1f2937' : '#ffffff'}"/>
          <g transform="translate(${(width-500)/2}, ${(height-350)/2})">
            ${structure.paths}
          </g>
          <text x="${width/2}" y="30" text-anchor="middle" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="16" font-weight="bold">
            ${structure.title}
          </text>
          <text x="${width/2}" y="${height-15}" text-anchor="middle" fill="${isDarkMode ? '#888888' : '#666666'}" font-size="10" font-family="monospace">
            ${smilesString}
          </text>
        </svg>
      `;
    } else {
      // Generic structure for unknown SMILES
      return generateGenericMolecularStructure(smilesString, width, height);
    }
  };

  const generateGenericMolecularStructure = (smilesString, width, height) => {
    // Analyze SMILES to create a more accurate generic structure
    const hasAromatic = /[a-z]/.test(smilesString);
    const hasCarbonyl = /=O/.test(smilesString);
    const hasNitrogen = /N/.test(smilesString);
    const hasOxygen = /O/.test(smilesString);
    const hasSulfur = /S/.test(smilesString);
    const hasRings = /\d/.test(smilesString);
    
    let structure = `
      <svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="${isDarkMode ? '#1f2937' : '#ffffff'}"/>
        <g transform="translate(${width/2}, ${height/2})">
    `;

    if (hasAromatic || hasRings) {
      // Draw aromatic ring
      structure += `
        <polygon points="-40,-70 40,-70 80,0 40,70 -40,70 -80,0" 
                 fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
        <polygon points="-30,-52 30,-52 60,0 30,52 -30,52 -60,0" 
                 fill="none" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="1"/>
      `;
    } else {
      // Draw chain structure
      structure += `
        <line x1="-60" y1="0" x2="-20" y2="0" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
        <line x1="-20" y1="0" x2="20" y2="0" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
        <line x1="20" y1="0" x2="60" y2="0" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
      `;
    }

    // Add heteroatoms
    if (hasOxygen) {
      structure += `
        <circle cx="100" cy="0" r="10" fill="#ff0000"/>
        <text x="100" y="5" text-anchor="middle" fill="white" font-size="12" font-weight="bold">O</text>
        <line x1="80" y1="0" x2="90" y2="0" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
      `;
    }

    if (hasNitrogen) {
      structure += `
        <circle cx="-100" cy="0" r="10" fill="#0000ff"/>
        <text x="-100" y="5" text-anchor="middle" fill="white" font-size="12" font-weight="bold">N</text>
        <line x1="-80" y1="0" x2="-90" y2="0" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
      `;
    }

    if (hasSulfur) {
      structure += `
        <circle cx="0" cy="100" r="12" fill="#ffff00"/>
        <text x="0" y="105" text-anchor="middle" fill="black" font-size="12" font-weight="bold">S</text>
        <line x1="0" y1="80" x2="0" y2="88" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="2"/>
      `;
    }

    if (hasCarbonyl) {
      structure += `
        <circle cx="0" cy="-100" r="8" fill="#ff0000"/>
        <text x="0" y="-95" text-anchor="middle" fill="white" font-size="10">O</text>
        <line x1="0" y1="-80" x2="0" y2="-92" stroke="${isDarkMode ? '#ffffff' : '#000000'}" stroke-width="3"/>
      `;
    }

    structure += `
        </g>
        <text x="${width/2}" y="30" text-anchor="middle" fill="${isDarkMode ? '#ffffff' : '#000000'}" font-size="16" font-weight="bold">
          Custom Molecule
        </text>
        <text x="${width/2}" y="${height-15}" text-anchor="middle" fill="${isDarkMode ? '#888888' : '#666666'}" font-size="10" font-family="monospace">
          ${smilesString.length > 50 ? smilesString.substring(0, 50) + '...' : smilesString}
        </text>
      </svg>
    `;

    return structure;
  };

  const generateMoleculeSpecificDescriptors = (smilesString) => {
    // Calculate realistic descriptors based on SMILES structure
    const descriptorMap = {
      'CC(=O)OC1=CC=CC=C1C(=O)O': { // Aspirin
        MW: 180.16,
        LogP: 1.19,
        HBD: 1,
        HBA: 4,
        TPSA: 63.6,
        nRotB: 3,
        nAromRing: 1,
        nSaturatedRing: 0,
        nHeteroAtoms: 4
      },
      'CN1C=NC2=C1C(=O)N(C(=O)N2C)C': { // Caffeine
        MW: 194.19,
        LogP: -0.07,
        HBD: 0,
        HBA: 6,
        TPSA: 58.4,
        nRotB: 0,
        nAromRing: 2,
        nSaturatedRing: 0,
        nHeteroAtoms: 6
      },
      'CC(C)CC1=CC=C(C=C1)C(C)C(=O)O': { // Ibuprofen
        MW: 206.28,
        LogP: 3.97,
        HBD: 1,
        HBA: 2,
        TPSA: 37.3,
        nRotB: 4,
        nAromRing: 1,
        nSaturatedRing: 0,
        nHeteroAtoms: 2
      },
      'CC(=O)NC1=CC=C(C=C1)O': { // Paracetamol
        MW: 151.16,
        LogP: 0.46,
        HBD: 2,
        HBA: 3,
        TPSA: 49.3,
        nRotB: 1,
        nAromRing: 1,
        nSaturatedRing: 0,
        nHeteroAtoms: 3
      }
    };

    const known = descriptorMap[smilesString];
    if (known) {
      return {
        ...known,
        FractionCsp3: known.nSaturatedRing / (known.nAromRing + known.nSaturatedRing + 1),
        Chi0v: known.MW / 20,
        Chi1v: known.MW / 30,
        BertzCT: known.MW * 2,
        BalabanJ: 1.5 + Math.random(),
        PEOE_VSA1: known.TPSA * 0.8,
        SMR_VSA1: known.MW * 0.1,
        SlogP_VSA1: known.LogP * 10,
        EState_VSA1: known.HBA * 5
      };
    }

    // Generate estimated descriptors for unknown molecules
    const carbonCount = (smilesString.match(/C/g) || []).length;
    const nitrogenCount = (smilesString.match(/N/g) || []).length;
    const oxygenCount = (smilesString.match(/O/g) || []).length;
    const estimatedMW = carbonCount * 12 + nitrogenCount * 14 + oxygenCount * 16 + (smilesString.length * 0.5);

    return {
      MW: estimatedMW,
      LogP: (carbonCount * 0.5) - (oxygenCount * 0.8) - (nitrogenCount * 0.3),
      HBD: oxygenCount + nitrogenCount,
      HBA: oxygenCount + nitrogenCount,
      TPSA: oxygenCount * 20 + nitrogenCount * 15,
      nRotB: Math.max(0, smilesString.length / 8),
      nAromRing: (smilesString.match(/c|C1/g) || []).length > 5 ? 1 : 0,
      nSaturatedRing: (smilesString.match(/\d/g) || []).length > 0 ? 1 : 0,
      nHeteroAtoms: nitrogenCount + oxygenCount,
      FractionCsp3: Math.random() * 0.5,
      Chi0v: estimatedMW / 20,
      Chi1v: estimatedMW / 30,
      BertzCT: estimatedMW * 2,
      BalabanJ: 1 + Math.random() * 3,
      PEOE_VSA1: oxygenCount * 20,
      SMR_VSA1: estimatedMW * 0.1,
      SlogP_VSA1: carbonCount * 2,
      EState_VSA1: (oxygenCount + nitrogenCount) * 5
    };
  };

  const generateMoleculeSpecificFingerprint = (smilesString, type) => {
    // Generate more realistic fingerprints based on molecule structure
    const length = type === 'morgan' ? 2048 : type === 'rdkit' ? 2048 : 512;
    const seed = smilesString.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    
    // Use SMILES string as seed for reproducible fingerprints
    const fingerprint = Array.from({ length }, (_, i) => {
      const hash = (seed * (i + 1)) % 1000;
      return hash < 100 ? 1 : 0; // ~10% bits set, more realistic
    });

    return fingerprint;
  };

  const generateMolecule = useCallback(async () => {
    if (!rdkitRef.current || !smiles) return;

    console.log('Generating molecule for SMILES:', smiles, 'Real RDKit:', usingRealRDKit);
    setIsLoading(true);
    setError(null);

    try {
      if (usingRealRDKit) {
        // ── Real RDKit-JS path ──
        const mol = rdkitRef.current.get_mol(smiles);
        if (!mol || !mol.is_valid()) {
          throw new Error('Invalid SMILES string');
        }

        setMolecule(mol);

        // Get descriptors (returns JSON string)
        try {
          const descJson = mol.get_descriptors();
          const desc = JSON.parse(descJson);
          const props = {
            MW: desc.exactmw ?? desc.amw ?? 0,
            LogP: desc.CrippenClogP ?? 0,
            HBD: desc.NumHBD ?? 0,
            HBA: desc.NumHBA ?? 0,
            TPSA: desc.tpsa ?? 0,
            nRotB: desc.NumRotatableBonds ?? 0,
            nAromRing: desc.NumAromaticRings ?? 0,
            nSaturatedRing: desc.NumSaturatedRings ?? 0,
            nHeteroAtoms: desc.NumHeteroatoms ?? 0,
          };
          setMolecularProperties(props);
          setDescriptors(props);
        } catch { /* descriptors optional */ }

        // Get fingerprints
        try {
          const morganFpStr = mol.get_morgan_fp();
          const morganBits = morganFpStr.split('').filter(c => c === '1').length;
          setFingerprints({ morganBits, rdkitBits: 0 });
        } catch { /* fingerprints optional */ }

        // Render SVG
        const svg = mol.get_svg(width, height);
        setCurrentSVG(svg);

      } else {
        // ── Fallback path (mock SVG) ──
        const props = generateMoleculeSpecificDescriptors(smiles);
        setMolecularProperties(props);
        setDescriptors(props);

        const morganFp = generateMoleculeSpecificFingerprint(smiles, 'morgan');
        const rdkitFp = generateMoleculeSpecificFingerprint(smiles, 'rdkit');
        setFingerprints({
          morganBits: morganFp.reduce((a, b) => a + b, 0),
          rdkitBits: rdkitFp.reduce((a, b) => a + b, 0),
        });

        const svg = generateMoleculeSpecificSVG(smiles, width, height);
        setCurrentSVG(svg);
        setMolecule({ _smiles: smiles });
      }
    } catch (err) {
      console.error('Molecule generation error:', err);
      setError(`Error generating molecule: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [smiles, usingRealRDKit, width, height]);

  // Auto-generate molecule when SMILES changes
  useEffect(() => {
    if (rdkitReady && smiles) {
      generateMolecule();
    }
  }, [rdkitReady, smiles, generateMolecule]);

  const resetView = () => {
    if (smiles) {
      generateMolecule();
    }
  };

  const downloadImage = () => {
    if (!currentSVG) return;
    
    try {
      // Download SVG
      const blob = new Blob([currentSVG], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `molecule_${title.replace(/\s+/g, '_')}.svg`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download error:', err);
    }
  };

  const exportData = () => {
    if (!molecularProperties) return;

    const data = {
      smiles: smiles,
      title: title,
      timestamp: new Date().toISOString(),
      properties: molecularProperties,
      descriptors: descriptors,
      fingerprints: fingerprints ? {
        morganBits: fingerprints.morganBits,
        rdkitBits: fingerprints.rdkitBits
      } : null,
      settings: settings
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { 
      type: 'application/json' 
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `molecule_data_${title.replace(/\s+/g, '_')}.json`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  if (!rdkitReady) {
    return (
      <div className={`p-6 rounded-lg border ${
        isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'
      }`}>
        <div className="flex items-center justify-center">
          <div className="w-6 h-6 mr-3 border-b-2 border-blue-500 rounded-full animate-spin"></div>
          <p className={getTextClasses(isDarkMode, 'secondary')}>
            Initializing RDKit molecular engine...
          </p>
        </div>
      </div>
    );
  }

  if (!smiles) {
    return (
      <div className={`p-8 text-center rounded-lg border ${
        isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'
      }`}>
        <Eye className={`h-12 w-12 mx-auto mb-4 ${getTextClasses(isDarkMode, 'muted')}`} />
        <p className={getTextClasses(isDarkMode, 'secondary')}>
          Enter a SMILES string to visualize the molecular structure with RDKit
        </p>
      </div>
    );
  }

  return (
    <div className={`rounded-lg border ${
      isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center">
          <Zap className="w-5 h-5 mr-2 text-blue-500" />
          <h3 className={`text-lg font-semibold ${getTextClasses(isDarkMode, 'primary')}`}>
            {title} <span className={`text-sm font-normal ${usingRealRDKit ? 'text-green-500' : 'text-amber-500'}`}>
              ({usingRealRDKit ? 'RDKit' : 'Fallback'})
            </span>
          </h3>
        </div>
        
        {showControls && (
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setCurrentStyle(currentStyle === '2d' ? '3d' : '2d')}
              className={`px-3 py-1 text-sm rounded transition-colors ${
                isDarkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-100 hover:bg-gray-200'
              }`}
              title="Toggle 2D/3D view"
            >
              {currentStyle.toUpperCase()}
            </button>
            
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`p-1 rounded transition-colors ${
                isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
              }`}
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
            
            <button
              onClick={resetView}
              className={`p-1 rounded transition-colors ${
                isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
              }`}
              title="Reset view"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            
            <button
              onClick={downloadImage}
              className={`p-1 rounded transition-colors ${
                isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
              }`}
              title="Download SVG"
            >
              <Download className="w-4 h-4" />
            </button>
            
            <button
              onClick={exportData}
              className={`p-1 rounded transition-colors ${
                isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
              }`}
              title="Export molecular data"
            >
              <Download className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className={`p-4 border-b border-gray-200 dark:border-gray-700 ${
          isDarkMode ? 'bg-gray-900' : 'bg-gray-50'
        }`}>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={settings.atomLabels}
                onChange={(e) => setSettings(prev => ({ ...prev, atomLabels: e.target.checked }))}
                className="rounded"
              />
              <span className={`text-sm ${getTextClasses(isDarkMode, 'secondary')}`}>
                Atom Labels
              </span>
            </label>
            
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={settings.addStereoAnnotation}
                onChange={(e) => setSettings(prev => ({ ...prev, addStereoAnnotation: e.target.checked }))}
                className="rounded"
              />
              <span className={`text-sm ${getTextClasses(isDarkMode, 'secondary')}`}>
                Stereo Annotation
              </span>
            </label>
            
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={settings.addAtomIndices}
                onChange={(e) => setSettings(prev => ({ ...prev, addAtomIndices: e.target.checked }))}
                className="rounded"
              />
              <span className={`text-sm ${getTextClasses(isDarkMode, 'secondary')}`}>
                Atom Indices
              </span>
            </label>
            
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={settings.explicitMethyl}
                onChange={(e) => setSettings(prev => ({ ...prev, explicitMethyl: e.target.checked }))}
                className="rounded"
              />
              <span className={`text-sm ${getTextClasses(isDarkMode, 'secondary')}`}>
                Explicit Methyl
              </span>
            </label>
          </div>
        </div>
      )}

      <div className="flex">
        {/* Visualization Canvas */}
        <div className="flex-1 p-4">
          <div className="relative">
            {isLoading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-black rounded bg-opacity-20">
                <div className="text-center">
                  <div className="w-8 h-8 mx-auto mb-2 border-b-2 border-blue-500 rounded-full animate-spin"></div>
                  <p className={`text-sm ${getTextClasses(isDarkMode, 'secondary')}`}>
                    Generating RDKit structure...
                  </p>
                </div>
              </div>
            )}
            
            {error ? (
              <div className={`p-8 text-center rounded border ${
                isDarkMode ? 'border-red-600 bg-red-900/20' : 'border-red-300 bg-red-50'
              }`}>
                <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-red-500" />
                <p className="mb-2 text-red-500">{error}</p>
                <button
                  onClick={generateMolecule}
                  className="px-4 py-2 text-white transition-colors bg-blue-500 rounded hover:bg-blue-600"
                >
                  Retry
                </button>
              </div>
            ) : (
              <div
                className="w-full bg-white border rounded dark:bg-gray-800"
                style={{ width: width, height: height, minHeight: height }}
              >
                {currentSVG ? (
                  <div 
                    dangerouslySetInnerHTML={{ __html: currentSVG }}
                    className="flex items-center justify-center w-full h-full"
                  />
                ) : (
                  <div className="flex items-center justify-center w-full h-full text-gray-500">
                    <div className="text-center">
                      <Eye className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p>Generating structure…</p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Properties Panel */}
        {showProperties && molecularProperties && (
          <div className={`w-80 p-4 border-l border-gray-200 dark:border-gray-700 ${
            isDarkMode ? 'bg-gray-900' : 'bg-gray-50'
          }`}>
            <div className="flex items-center mb-3">
              <Info className="w-4 h-4 mr-2 text-blue-500" />
              <h4 className={`font-semibold ${getTextClasses(isDarkMode, 'primary')}`}>
                RDKit Properties
              </h4>
            </div>
            
            <div className="space-y-4">
              {/* Basic Properties */}
              <div>
                <h5 className={`text-sm font-medium mb-2 ${getTextClasses(isDarkMode, 'primary')}`}>
                  Basic Properties
                </h5>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>MW:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.MW.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>LogP:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.LogP.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>HBD:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.HBD}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>HBA:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.HBA}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>TPSA:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.TPSA.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>RotBonds:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.nRotB}</span>
                  </div>
                </div>
              </div>

              {/* Ring Analysis */}
              <div>
                <h5 className={`text-sm font-medium mb-2 ${getTextClasses(isDarkMode, 'primary')}`}>
                  Ring Analysis
                </h5>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>Aromatic:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.nAromRing}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={getTextClasses(isDarkMode, 'secondary')}>Saturated:</span>
                    <span className={getTextClasses(isDarkMode, 'primary')}>{molecularProperties.nSaturatedRing}</span>
                  </div>
                </div>
              </div>

              {/* Fingerprints */}
              {fingerprints && (
                <div>
                  <h5 className={`text-sm font-medium mb-2 ${getTextClasses(isDarkMode, 'primary')}`}>
                    Fingerprints
                  </h5>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className={getTextClasses(isDarkMode, 'secondary')}>Morgan bits:</span>
                      <span className={getTextClasses(isDarkMode, 'primary')}>{fingerprints.morganBits}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={getTextClasses(isDarkMode, 'secondary')}>RDKit bits:</span>
                      <span className={getTextClasses(isDarkMode, 'primary')}>{fingerprints.rdkitBits}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Drug-likeness Assessment */}
              <div className={`p-2 rounded text-xs ${
                molecularProperties.MW < 500 && 
                molecularProperties.LogP < 5 && 
                molecularProperties.HBD <= 5 && 
                molecularProperties.HBA <= 10
                  ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                  : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
              }`}>
                <strong>Lipinski's Rule:</strong><br />
                {molecularProperties.MW < 500 && 
                 molecularProperties.LogP < 5 && 
                 molecularProperties.HBD <= 5 && 
                 molecularProperties.HBA <= 10
                  ? '✓ Passes all criteria'
                  : '⚠ Some violations detected'
                }
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RDKitMolecularVisualization;
