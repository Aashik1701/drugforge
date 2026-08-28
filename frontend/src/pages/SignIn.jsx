import React from 'react';
import AuthForm from '../components/AuthForm';
import ErrorBoundary from '../components/ErrorBoundary';

const SignInPage = () => {
  return (
    <ErrorBoundary>
      <AuthForm mode="login" />
    </ErrorBoundary>
  );
};

export default SignInPage;
