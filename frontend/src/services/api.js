/**
 * API service for DrugForge AI
 * Handles communication with backend ML models and services
 */

import axios from 'axios';

// Base API URL - FastAPI backend on port 5001
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';

// Create axios instance with base config
const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30s timeout for ML predictions
});

// Request interceptor for adding auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for handling errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const { response, config } = error;
    
    // Handle specific error codes
    if (response && response.status === 401) {
      // Don't redirect for auth check endpoints (AuthContext probing)
      const isAuthCheck = config?.url?.includes('/auth/');
      if (!isAuthCheck) {
        localStorage.removeItem('token');
        window.location.href = '/signin';
      }
    }

    if (response && response.status === 503) {
      console.error('Service unavailable - ML model may not be loaded');
    }

    return Promise.reject(error);
  }
);

// Drug prediction endpoints
export const predictionService = {
  predictSolubility: (smiles) => apiClient.post('/predict/solubility', { smiles }),
  predictBBBP: (smiles) => apiClient.post('/predict/bbbp', { smiles }),
  predictCYP3A4: (smiles) => apiClient.post('/predict/cyp3a4', { smiles }),
  predictHalfLife: (smiles) => apiClient.post('/predict/half-life', { smiles }),
  predictCOX2: (smiles) => apiClient.post('/predict/cox2', { smiles }),
  predictHEPG2: (smiles) => apiClient.post('/predict/hepg2', { smiles }),
  predictBindingScore: (smiles, targetId) => apiClient.post('/predict/binding-score', { smiles, target_id: targetId }),
  predictACE2: (smiles) => apiClient.post('/predict/ace2', { smiles }),
  predictToxicity: (smiles) => apiClient.post('/predict/toxicity', { smiles }),
};

// Health check
export const healthService = {
  check: () => apiClient.get('/health'),
  listModels: () => apiClient.get('/models'),
};

export const dockingService = {
  startDocking: (smiles, target, exhaustiveness) =>
    apiClient.post('/api/dock/start', { smiles, target, exhaustiveness }, { timeout: 120000 }),
  getDockingStatus: (taskId) =>
    apiClient.get(`/api/dock/status/${taskId}`, { timeout: 15000 }),
  cancelDocking: (taskId) =>
    apiClient.post(`/api/dock/cancel/${taskId}`, {}, { timeout: 10000 }),
  getHistory: () =>
    apiClient.get('/api/dock/history', { timeout: 15000 }),
  getReceptor: (target) =>
    apiClient.get(`/api/dock/receptor/${target}`, { timeout: 60000 }),
};

export const computeService = {
  getPolicy: () => apiClient.get('/api/compute/policy'),
  setMode: (mode) => apiClient.post('/api/compute/mode', { mode }),
};

export { apiClient };

export default {
  predictionService,
  healthService,
  dockingService,
  computeService,
};
