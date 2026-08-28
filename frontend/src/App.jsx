// App.js — DrugForge 2.0 "Glass Laboratory"
// Consolidated from 22+ routes down to 5 core routes
// Public routes → GlassHeader (top floating nav)
// App routes   → Sidebar + inner Header via GlassLayout
import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import './index.css';

// Context Providers
import { DrugForgeProvider } from './context/DrugForgeContext.jsx';
import { AuthProvider } from './context/AuthContext.jsx';

// Layout Components (always loaded)
import GlassHeader from './components/GlassHeader.jsx';
import GlassLayout from './components/layout/GlassLayout.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import Notifications from './components/Notifications.jsx';
import ChatWidget from './components/ChatWidget.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import { ThemeProvider } from './components/ThemeProvider.jsx';
import GlassBackground from './components/layout/GlassBackground.jsx';

// Shimmer Loading Fallback
export const LoadingFallback = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="relative">
      <div className="w-16 h-16 border-4 rounded-full border-cyan-500/20 border-t-cyan-500 animate-spin" />
      <div className="absolute inset-0 w-16 h-16 border-4 rounded-full border-violet-500/20 border-t-violet-500 animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
    </div>
  </div>
);

// ─── Core 5 Routes (Lazy-loaded) ──────────────────────────────
const LandingPage = lazy(() => import('./pages/LandingPage.jsx'));
const AppDashboard = lazy(() => import('./components/AppDashboard.jsx'));
const LabBench = lazy(() => import('./components/LabBench.jsx'));
const BatchProcessor = lazy(() => import('./components/BatchProcessor.jsx'));
const UserSettings = lazy(() => import('./components/UserSettings.jsx'));
const DockingStudio = lazy(() => import('./components/DockingStudio.jsx'));
const NotFound = lazy(() => import('./pages/NotFound.jsx'));

// Auth pages (still needed)
const RegisterPage = lazy(() => import('./pages/Register.jsx'));
const SignInPage = lazy(() => import('./pages/SignIn.jsx'));

// Kept for direct access (visualizations)
const MolecularVisualizationPage = lazy(() => import('./components/MolecularVisualizationPage.jsx'));

// ─── Inner shell: uses useLocation to swap between public/app layouts ───
const AppContent = () => {
  const location = useLocation();
  const isAppRoute = location.pathname.startsWith('/app');

  return (
    <>
      {/* Public routes get the floating GlassHeader; app routes get the Sidebar via GlassLayout */}
      {!isAppRoute && <GlassHeader />}
      <Notifications />
      <ChatWidget />

      <Suspense fallback={<LoadingFallback />}>
        <div className={!isAppRoute ? 'pt-18 min-h-screen text-gray-900 dark:text-gray-100' : 'text-gray-900 dark:text-gray-100'}>
          <Routes>
            {/* ═══ 1. Public Landing Page ═══ */}
            <Route path="/" element={<LandingPage />} />

            {/* ═══ 2. App Dashboard (Sidebar layout, protected) ═══ */}
            <Route path="/app" element={<ProtectedRoute><GlassLayout><AppDashboard /></GlassLayout></ProtectedRoute>} />

            {/* ═══ 3. Lab Bench (replaces 9 prediction routes) ═══ */}
            <Route path="/app/analyze" element={<ProtectedRoute><GlassLayout><LabBench /></GlassLayout></ProtectedRoute>} />

            {/* ═══ 4. Batch Processor ═══ */}
            <Route path="/app/batch" element={<ProtectedRoute><GlassLayout><BatchProcessor /></GlassLayout></ProtectedRoute>} />

            {/* ═══ 5. User Settings ═══ */}
            <Route path="/app/settings" element={<ProtectedRoute><GlassLayout><UserSettings /></GlassLayout></ProtectedRoute>} />

            {/* Docking Studio */}
            <Route path="/app/docking" element={<ProtectedRoute><GlassLayout><DockingStudio /></GlassLayout></ProtectedRoute>} />

            {/* Auth */}
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/signin" element={<SignInPage />} />

            {/* Molecular Visualization (standalone tool, protected) */}
            <Route path="/app/visualization" element={<ProtectedRoute><GlassLayout><MolecularVisualizationPage /></GlassLayout></ProtectedRoute>} />
            <Route path="/molecular-visualization" element={<Navigate to="/app/visualization" replace />} />

            {/* ═══ Legacy Redirects → Lab Bench ═══ */}
            <Route path="/dashboard" element={<Navigate to="/app" replace />} />
            <Route path="/solubility-checker" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/cyp3a4-predictor" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/half-life" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/cox2" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/hepg2" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/bbbp" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/binding-score" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/ace2" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/toxicity" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/virtual-screening" element={<Navigate to="/app/analyze" replace />} />
            <Route path="/batch-prediction" element={<Navigate to="/app/batch" replace />} />
            <Route path="/features" element={<Navigate to="/#features" replace />} />
            <Route path="/services" element={<Navigate to="/" replace />} />
            <Route path="/pricing" element={<Navigate to="/#pricing" replace />} />
            <Route path="/contact" element={<Navigate to="/" replace />} />
            <Route path="/profile" element={<Navigate to="/app/settings" replace />} />
            <Route path="/docking-studio" element={<Navigate to="/app/docking" replace />} />

            {/* Not Found */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </Suspense>

      <ChatWidget />
    </>
  );
};

const App = () => {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <DrugForgeProvider>
          <ThemeProvider>
            <GlassBackground>
              <AppContent />
            </GlassBackground>
          </ThemeProvider>
        </DrugForgeProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
};

export default App;
