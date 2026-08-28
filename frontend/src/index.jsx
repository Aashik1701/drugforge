import React from 'react';
import ReactDOM from 'react-dom/client'; // Use this import for React 18+
import App from './App.jsx';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './index.css';

const queryClient = new QueryClient();

// Performance mode: reduces continuous decorative animation (aurora, meteor,
// glow, shimmer — see index.css). Explicit VITE_PERFORMANCE_MODE wins;
// otherwise defaults to on in dev, off in production (spec §21).
const envPerfMode = import.meta.env.VITE_PERFORMANCE_MODE;
const performanceMode = envPerfMode !== undefined ? envPerfMode === 'true' : import.meta.env.DEV;
document.documentElement.dataset.performanceMode = String(performanceMode);

// Suppress unhandled promise rejections from browser extensions
// (e.g., {name: 'n', httpError: false, httpStatus: 200, code: 403})
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason;
  if (reason && typeof reason === 'object' && 'httpError' in reason && 'httpStatus' in reason) {
    // This is a browser extension error, not from our app
    event.preventDefault();
  }
});

// Create a root for rendering
const root = ReactDOM.createRoot(document.getElementById('root')); 

// Render the app
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter
        future={{
          v7_relativeSplatPath: true,
          v7_startTransition: true,
        }}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
