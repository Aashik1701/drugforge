import React, { createContext, useState, useEffect, useContext, useCallback } from 'react';

// Create the auth context
const AuthContext = createContext();

// Auth Provider component — localStorage-based (no backend auth endpoints needed)
export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Restore user from localStorage on mount
  useEffect(() => {
    try {
      const token = localStorage.getItem('authToken');
      const storedUser = localStorage.getItem('user');
      if (token && storedUser) {
        setUser(JSON.parse(storedUser));
      }
    } catch (err) {
      console.debug('Auth restore failed:', err.message);
      localStorage.removeItem('authToken');
      localStorage.removeItem('user');
    } finally {
      setLoading(false);
    }
  }, []);

  // Login function (mock — validates locally)
  const login = useCallback(async (email, password) => {
    try {
      setError(null);
      setLoading(true);

      if (!email || !email.includes('@')) {
        throw new Error('Please enter a valid email address');
      }
      if (!password || password.length < 6) {
        throw new Error('Password must be at least 6 characters');
      }

      // Simulate brief API delay
      await new Promise(r => setTimeout(r, 500));

      const userData = {
        id: 'user-' + Date.now(),
        email,
        name: email.split('@')[0],
        role: 'user',
        createdAt: new Date().toISOString(),
      };

      localStorage.setItem('authToken', 'mock-jwt-' + Date.now());
      localStorage.setItem('user', JSON.stringify(userData));
      setUser(userData);
      return { success: true, user: userData };
    } catch (err) {
      const message = err.message || 'Login failed';
      setError(message);
      return { success: false, message };
    } finally {
      setLoading(false);
    }
  }, []);

  // Register function (mock — validates locally)
  const register = useCallback(async (email, password, name) => {
    try {
      setError(null);
      setLoading(true);

      if (!email || !email.includes('@')) {
        throw new Error('Please enter a valid email address');
      }
      if (!password || password.length < 6) {
        throw new Error('Password must be at least 6 characters');
      }
      if (!name || name.trim().length < 2) {
        throw new Error('Please enter your name');
      }

      await new Promise(r => setTimeout(r, 600));

      const userData = {
        id: 'user-' + Date.now(),
        email,
        name,
        role: 'user',
        createdAt: new Date().toISOString(),
      };

      localStorage.setItem('authToken', 'mock-jwt-' + Date.now());
      localStorage.setItem('user', JSON.stringify(userData));
      setUser(userData);
      return { success: true, user: userData };
    } catch (err) {
      const message = err.message || 'Registration failed';
      setError(message);
      return { success: false, message };
    } finally {
      setLoading(false);
    }
  }, []);

  // Logout function
  const logout = useCallback(() => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    setUser(null);
    setError(null);
  }, []);

  // Update profile (persists to localStorage)
  const updateProfile = useCallback(async (profileData) => {
    try {
      setLoading(true);
      const updated = { ...user, ...profileData };
      localStorage.setItem('user', JSON.stringify(updated));
      setUser(updated);
      return { success: true };
    } catch (err) {
      setError(err.message);
      return { success: false, message: err.message };
    } finally {
      setLoading(false);
    }
  }, [user]);

  const value = {
    user,
    loading,
    error,
    login,
    register,
    logout,
    updateProfile,
    isAuthenticated: !!user,
    isLoggedIn: !!user,         // alias for hooks/useAuth compat
    isLoading: loading,         // alias for hooks/useAuth compat
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// Custom hook for using the auth context
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
