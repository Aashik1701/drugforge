import React, { useState } from 'react';
import { useNavigate, Navigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ErrorBoundary from './ErrorBoundary';
import { AlertCircle, Loader2, CheckCircle, LogIn } from 'lucide-react';

/**
 * Authentication component that handles both login and registration
 */
const AuthForm = ({ mode = 'login' }) => {
  // State for form fields
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // Form validation
  const [formError, setFormError] = useState('');
  const [formSuccess, setFormSuccess] = useState('');
  
  // Auth hook
  const { login, register, isLoading, error, isLoggedIn } = useAuth();
  const navigate = useNavigate();
  
  // If already logged in, redirect to dashboard
  if (isLoggedIn) {
    return <Navigate to="/dashboard" replace />;
  }
  
  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');
    
    // Basic validation
    if (!email) {
      setFormError('Email is required');
      return;
    }
    
    if (!password) {
      setFormError('Password is required');
      return;
    }
    
    if (mode === 'register') {
      if (!name) {
        setFormError('Name is required');
        return;
      }
      
      if (password !== confirmPassword) {
        setFormError('Passwords do not match');
        return;
      }
    }
    
    try {
      if (mode === 'login') {
        await login(email, password);
        setFormSuccess('Login successful!');
        // Redirect after short delay to show success message
        setTimeout(() => {
          navigate('/dashboard');
        }, 1000);
      } else {
        await register(email, password, name);
        setFormSuccess('Registration successful!');
        // Redirect after short delay to show success message
        setTimeout(() => {
          navigate('/dashboard');
        }, 1000);
      }
    } catch (err) {
      setFormError(err.message || 'Authentication failed. Please try again.');
    }
  };
  
  return (
    <ErrorBoundary>
      <div className="flex items-center justify-center min-h-screen px-4 py-12 bg-gray-50 dark:bg-gray-900 sm:px-6 lg:px-8">
        <div className="w-full max-w-md space-y-8">
          {/* Header */}
          <div>
            <h2 className="mt-6 text-3xl font-extrabold text-center text-gray-900 dark:text-gray-100">
              {mode === 'login' ? 'Sign in to your account' : 'Create a new account'}
            </h2>
            <p className="mt-2 text-sm text-center text-gray-600 dark:text-gray-400">
              {mode === 'login' ? 'New to DrugForge?' : 'Already have an account?'}{' '}
              <Link
                to={mode === 'login' ? '/register' : '/signin'}
                className="font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300"
              >
                {mode === 'login' ? 'Register now' : 'Sign in'}
              </Link>
            </p>
          </div>

          {/* Form */}
          <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-4 rounded-md shadow-sm">
              {/* Name field (register only) */}
              {mode === 'register' && (
                <div>
                  <label htmlFor="name" className="sr-only">
                    Full Name
                  </label>
                  <input
                    id="name"
                    name="name"
                    type="text"
                    autoComplete="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="relative block w-full px-3 py-2 text-gray-900 placeholder-gray-500 bg-white border border-gray-300 rounded-md appearance-none dark:border-gray-600 dark:text-gray-100 dark:bg-gray-800 dark:placeholder-gray-400 focus:z-10 focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                    placeholder="Full Name"
                  />
                </div>
              )}

              {/* Email field */}
              <div>
                <label htmlFor="email-address" className="sr-only">
                  Email address
                </label>
                <input
                  id="email-address"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="relative block w-full px-3 py-2 text-gray-900 placeholder-gray-500 bg-white border border-gray-300 rounded-md appearance-none dark:border-gray-600 dark:text-gray-100 dark:bg-gray-800 dark:placeholder-gray-400 focus:z-10 focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                  placeholder="Email address"
                />
              </div>

              {/* Password field */}
              <div>
                <label htmlFor="password" className="sr-only">
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="relative block w-full px-3 py-2 text-gray-900 placeholder-gray-500 bg-white border border-gray-300 rounded-md appearance-none dark:border-gray-600 dark:text-gray-100 dark:bg-gray-800 dark:placeholder-gray-400 focus:z-10 focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                  placeholder="Password"
                />
              </div>

              {/* Confirm password field (register only) */}
              {mode === 'register' && (
                <div>
                  <label htmlFor="confirm-password" className="sr-only">
                    Confirm Password
                  </label>
                  <input
                    id="confirm-password"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="relative block w-full px-3 py-2 text-gray-900 placeholder-gray-500 bg-white border border-gray-300 rounded-md appearance-none dark:border-gray-600 dark:text-gray-100 dark:bg-gray-800 dark:placeholder-gray-400 focus:z-10 focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                    placeholder="Confirm Password"
                  />
                </div>
              )}
            </div>

            {/* Error message */}
            {(formError || error) && (
              <div className="flex items-center p-3 space-x-2 text-sm text-red-700 rounded-md bg-red-50 dark:bg-red-900/30 dark:text-red-300">
                <AlertCircle className="w-5 h-5 text-red-500 dark:text-red-400" />
                <p>{formError || error}</p>
              </div>
            )}

            {/* Success message */}
            {formSuccess && (
              <div className="flex items-center p-3 space-x-2 text-sm text-green-700 rounded-md bg-green-50 dark:bg-green-900/30 dark:text-green-300">
                <CheckCircle className="w-5 h-5 text-green-500 dark:text-green-400" />
                <p>{formSuccess}</p>
              </div>
            )}

            {/* Form actions */}
            <div>
              <button
                type="submit"
                disabled={isLoading}
                className="relative flex justify-center w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md group dark:bg-blue-700 hover:bg-blue-700 dark:hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
              >
                <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                  {isLoading ? (
                    <Loader2 className="w-5 h-5 text-blue-300 animate-spin" />
                  ) : (
                    <LogIn className="w-5 h-5 text-blue-300" />
                  )}
                </span>
                {mode === 'login'
                  ? isLoading
                    ? 'Signing in...'
                    : 'Sign in'
                  : isLoading
                  ? 'Registering...'
                  : 'Register'}
              </button>
            </div>
          </form>

          {/* Helper text */}
          <div className="mt-6">
            <p className="text-sm text-center text-gray-600">
              By {mode === 'login' ? 'signing in' : 'registering'}, you agree to our{' '}
              <Link to="/terms" className="font-medium text-blue-600 hover:text-blue-500">
                Terms of Service
              </Link>{' '}
              and{' '}
              <Link to="/privacy" className="font-medium text-blue-600 hover:text-blue-500">
                Privacy Policy
              </Link>
              .
            </p>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default AuthForm;
