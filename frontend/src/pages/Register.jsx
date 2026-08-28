import React from 'react';
import AuthForm from '../components/AuthForm';
import ErrorBoundary from '../components/ErrorBoundary';

/**
 * Register page component using AuthForm with Tailwind CSS
 * Styled with dark/light theme support
 */
const RegisterPage = () => {
  return (
    <ErrorBoundary>
      <AuthForm mode="register" />
    </ErrorBoundary>
  );
};

export default RegisterPage;