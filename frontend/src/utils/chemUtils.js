/**
 * Utility functions for chemical structure handling
 */

// Convert SMILES to molecule object
export const smilesParser = (smiles) => {
  try {
    // This is a placeholder - in a real application, you would use
    // a library like RDKit.js or OpenChemLib to parse SMILES
    return { valid: true, smiles };
  } catch (error) {
    return { valid: false, error: 'Invalid SMILES string' };
  }
};

// Validate SMILES string format
export const validateSmiles = (smiles) => {
  if (!smiles || typeof smiles !== 'string') {
    return { valid: false, error: 'SMILES string is required' };
  }
  
  // Basic length check
  if (smiles.length < 3) {
    return { valid: false, error: 'SMILES string too short' };
  }
  
  if (smiles.length > 1000) {
    return { valid: false, error: 'SMILES string too long' };
  }
  
  // Check for basic SMILES characters
  const validSmilesPattern = /^[a-zA-Z0-9@+\-\[\]\(\)\\\/%=#\.\:]+$/;
  if (!validSmilesPattern.test(smiles)) {
    return { valid: false, error: 'Contains invalid characters' };
  }
  
  // Check for balanced brackets and parentheses
  const brackets = { '[': 0, '(': 0 };
  for (let char of smiles) {
    if (char === '[') brackets['[']++;
    if (char === ']') brackets['[']--;
    if (char === '(') brackets['(']++;
    if (char === ')') brackets['(']--;
    if (brackets['['] < 0 || brackets['('] < 0) {
      return { valid: false, error: 'Unbalanced brackets or parentheses' };
    }
  }
  
  if (brackets['['] !== 0 || brackets['('] !== 0) {
    return { valid: false, error: 'Unbalanced brackets or parentheses' };
  }
  
  return { valid: true };
};

// Format prediction results for display
export const formatPredictionResult = (result, type) => {
  switch (type) {
    case 'solubility':
      return {
        value: parseFloat(result.value).toFixed(2),
        unit: 'log(mol/L)',
        interpretation: interpretSolubility(result.value),
      };
    case 'bbbp':
      return {
        value: result.value > 0.5 ? 'Permeable' : 'Non-permeable',
        probability: (result.value * 100).toFixed(1) + '%',
      };
    case 'halfLife':
      return {
        value: parseFloat(result.value).toFixed(1),
        unit: 'hours',
        interpretation: interpretHalfLife(result.value),
      };
    default:
      return result;
  }
};

// Helper functions for result interpretation
const interpretSolubility = (value) => {
  if (value > 0) return 'Highly soluble';
  if (value > -2) return 'Soluble';
  if (value > -4) return 'Moderately soluble';
  return 'Poorly soluble';
};

const interpretHalfLife = (value) => {
  if (value < 1) return 'Very short half-life';
  if (value < 4) return 'Short half-life';
  if (value < 12) return 'Medium half-life';
  if (value < 24) return 'Long half-life';
  return 'Very long half-life';
};

/**
 * Date and time formatting utilities
 */

// Format date in user-friendly way
export const formatDate = (dateString) => {
  const options = { year: 'numeric', month: 'long', day: 'numeric' };
  return new Date(dateString).toLocaleDateString(undefined, options);
};

// Format date with time
export const formatDateTime = (dateString) => {
  const options = { 
    year: 'numeric', 
    month: 'short', 
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  };
  return new Date(dateString).toLocaleDateString(undefined, options);
};

// Get time elapsed since date
export const timeAgo = (dateString) => {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);
  
  let interval = Math.floor(seconds / 31536000);
  if (interval >= 1) {
    return interval + (interval === 1 ? ' year' : ' years') + ' ago';
  }
  
  interval = Math.floor(seconds / 2592000);
  if (interval >= 1) {
    return interval + (interval === 1 ? ' month' : ' months') + ' ago';
  }
  
  interval = Math.floor(seconds / 86400);
  if (interval >= 1) {
    return interval + (interval === 1 ? ' day' : ' days') + ' ago';
  }
  
  interval = Math.floor(seconds / 3600);
  if (interval >= 1) {
    return interval + (interval === 1 ? ' hour' : ' hours') + ' ago';
  }
  
  interval = Math.floor(seconds / 60);
  if (interval >= 1) {
    return interval + (interval === 1 ? ' minute' : ' minutes') + ' ago';
  }
  
  return 'just now';
};
