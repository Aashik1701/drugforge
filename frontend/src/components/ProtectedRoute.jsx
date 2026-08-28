import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LoadingFallback } from '../App.jsx';

/**
 * Component to protect routes that require authentication
 */
const ProtectedRoute = ({ redirectPath = '/signin', children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  // Show loading spinner while checking auth status
  if (loading) {
    return <LoadingFallback />;
  }

  // If not authenticated, redirect to login page
  if (!isAuthenticated) {
    // Save the current location to redirect after login
    return <Navigate to={redirectPath} state={{ from: location }} replace />;
  }

  // If authenticated, render children or outlet
  return children || <Outlet />;
};

export default ProtectedRoute;
