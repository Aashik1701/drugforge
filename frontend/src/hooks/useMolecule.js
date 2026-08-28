// Custom hook for molecule data handling
import { useState, useCallback } from 'react';
import { useDrugForge } from '../context/DrugForgeContext.jsx';
import { useApi } from './useApi';

/**
 * Custom hook for handling molecule data and predictions
 * Provides a standardized way to work with molecular structures and predictions
 */
export const useMolecule = () => {
  const [molecule, setMolecule] = useState(null);
  const [smiles, setSmiles] = useState('');
  const [isValidSmiles, setIsValidSmiles] = useState(true);
  const { addSearch } = useDrugForge();
  const { post, loading, error, data, resetError } = useApi();

  /**
   * Validate a SMILES string format (basic validation)
   * @param {string} smilesString - The SMILES string to validate
   * @returns {boolean} Whether the string appears to be valid SMILES
   */
  const validateSmiles = useCallback((smilesString) => {
    // This is a very basic validation - in production, you might want to use RDKit or another
    // cheminformatics library to properly validate SMILES strings
    if (!smilesString?.trim()) {
      return false;
    }

    // Basic validation: SMILES strings typically contain letters, numbers, and special characters
    // like =, (, ), [, ], #, etc.
    const basicSmilesPattern = /^[A-Za-z0-9@+\-\[\]\(\)\\\/%=#:.~]+$/;
    return basicSmilesPattern.test(smilesString.trim());
  }, []);

  /**
   * Handle SMILES input change with validation
   * @param {string} newSmiles - The new SMILES string
   */
  const handleSmilesChange = useCallback((newSmiles) => {
    setSmiles(newSmiles);
    setIsValidSmiles(validateSmiles(newSmiles));
    resetError();
  }, [validateSmiles, resetError]);

  /**
   * Submit a SMILES string for prediction
   * @param {string} endpoint - The API endpoint to call
   * @param {Object} additionalData - Additional data to include in the API call
   */
  const submitSmiles = useCallback(async (endpoint, additionalData = {}) => {
    if (!validateSmiles(smiles)) {
      setIsValidSmiles(false);
      return null;
    }

    try {
      const result = await post(endpoint, { 
        smiles, 
        ...additionalData 
      });
      
      // Save to recent searches
      addSearch({
        id: Date.now(),
        type: endpoint.split('/').pop(), // Use the endpoint name as type
        smiles,
        timestamp: new Date().toISOString(),
        result: result
      });
      
      return result;
    } catch (err) {
      console.error("Error submitting SMILES:", err);
      return null;
    }
  }, [smiles, validateSmiles, post, addSearch]);

  /**
   * Get 3D structure visualization data for a molecule
   * This is a placeholder - in a real app, you would call a service that returns
   * 3D coordinates or a visualization URL
   */
  const get3DStructure = useCallback(async () => {
    if (!validateSmiles(smiles)) {
      return null;
    }
    
    // This would normally call an API to get 3D structure
    // For now, we'll just return the SMILES
    return { smiles, format: '2D' };
  }, [smiles, validateSmiles]);

  return {
    smiles,
    setSmiles: handleSmilesChange,
    isValidSmiles,
    validateSmiles,
    molecule,
    setMolecule,
    submitSmiles,
    get3DStructure,
    loading,
    error,
    data
  };
};
